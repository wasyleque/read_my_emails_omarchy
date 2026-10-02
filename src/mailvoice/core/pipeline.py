"""Moduł potoku przetwarzania poczty (pipeline) - czysta logika bez Qt i audio."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Sequence

from mailvoice.core.analyzer import (
    AnalyzerError,
    AnalyzerFormatError,
    AnalyzerTransportError,
    OllamaClient,
    build_messages,
    pick_model,
)
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.friendly_errors import format_friendly_error
from mailvoice.core.imap_fetch import (
    MailboxClient,
    commit_progress,
    fetch_backlog,
    fetch_new,
    fetch_sent_for_index,
    fetch_sent_message_ids,
)
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.phishing import assess as phishing_assess
from mailvoice.core.rules import MailInfo, Rules
from mailvoice.core.rules import evaluate as rules_evaluate
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.core.threading import thread_key


def _index_mail(
    store: Store,
    account: str,
    folder: str,
    uidvalidity: int,
    uid: int,
    mail: ParsedMail,
    importance: int,
    why: str,
    summary: str = "",
    direction: str = "in",
    risk: str = "low",
    risk_reasons: str = "",
) -> None:
    """Zapisuje metadane i podsumowanie przetworzonej wiadomości do tabeli mail_index."""
    date_str = mail.date.isoformat() if mail.date else datetime.now(timezone.utc).isoformat()
    recipients_list = [*mail.to, *mail.cc]
    recipients_str = ", ".join(recipients_list)
    key = thread_key(mail)
    record = MailIndexRecord(
        account=account,
        folder=folder,
        uidvalidity=uidvalidity,
        uid=uid,
        message_id=mail.message_id,
        thread_key=key,
        date=date_str,
        sender=mail.sender,
        recipients=recipients_str,
        subject=mail.subject,
        importance=importance,
        why=why,
        summary=summary,
        direction=direction,
        risk=risk,
        risk_reasons=risk_reasons,
    )
    store.save_mail_index(record)
    store.invalidate_topic_digest_cache(key)


@dataclass(frozen=True)
class ProcessedMail:
    """Reprezentacja przetworzonej wiadomości e-mail."""

    account: str
    folder: str
    uidvalidity: int
    uid: int
    mail: ParsedMail
    final_importance: int
    rule_reasons: tuple[str, ...]
    analysis_reason: str
    action: str
    language: str
    suspicious: bool = False
    risk_level: str = "low"
    risk_reasons: tuple[str, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class PendingBacklog:
    """Oczekująca na decyzję użytkownika zaległa wiadomość odtworzona z bazy seen."""

    account: str
    folder: str
    uidvalidity: int
    uid: int
    message_id: str | None
    importance: int | None


@dataclass
class CycleResult:
    """Wynik wykonania cyklu sprawdzania poczty."""

    important: list[ProcessedMail] = field(default_factory=list)
    backlog_important: list[ProcessedMail] = field(default_factory=list)
    suspicious: list[ProcessedMail] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def resolve_backlog(self, store: Store, accepted: bool) -> None:
        """Rozstrzyga status ważnych zaległych wiadomości po odpowiedzi użytkownika."""
        resolve_backlog(store, self.backlog_important, accepted)


@dataclass
class PipelineDeps:
    """Zależności wstrzykiwane do potoku przetwarzania."""

    config: AppConfig
    store: Store
    client_factory: Callable[[AccountConfig], MailboxClient]
    ollama_client: OllamaClient


def resolve_backlog(
    store: Store, items: Sequence[ProcessedMail | PendingBacklog], accepted: bool
) -> None:
    """Oznacza zaległe wiadomości w bazie store w zależności od decyzji użytkownika.

    accepted=True -> status 'analyzed'
    accepted=False -> status 'backlog_declined'
    """
    status = "analyzed" if accepted else "backlog_declined"
    for item in items:
        mid = getattr(item, "message_id", None)
        if mid is None and hasattr(item, "mail"):
            mid = item.mail.message_id
        imp = getattr(item, "importance", None)
        if imp is None and hasattr(item, "final_importance"):
            imp = item.final_importance
        store.mark_seen(
            account=item.account,
            folder=item.folder,
            uidvalidity=item.uidvalidity,
            uid=item.uid,
            message_id=mid,
            status=status,
            importance=imp,
        )


def load_pending_backlog(store: Store, account: str | None = None) -> list[PendingBacklog]:
    """Odczytuje z bazy seen wiadomości ze statusem 'backlog_pending' (np. po restarcie)."""
    cursor = store.connection.cursor()
    if account:
        cursor.execute(
            """
            SELECT account, folder, uidvalidity, uid, message_id, importance
            FROM seen
            WHERE status = 'backlog_pending' AND account = ?
            ORDER BY uid ASC
            """,
            (account,),
        )
    else:
        cursor.execute(
            """
            SELECT account, folder, uidvalidity, uid, message_id, importance
            FROM seen
            WHERE status = 'backlog_pending'
            ORDER BY uid ASC
            """
        )
    rows = cursor.fetchall()
    return [
        PendingBacklog(
            account=r[0],
            folder=r[1],
            uidvalidity=r[2],
            uid=r[3],
            message_id=r[4],
            importance=r[5],
        )
        for r in rows
    ]


def _rule_bonus(rule_res, risk: str) -> int:
    """Premia z reguł; „znany korespondent” NIE liczy się przy podejrzanym mailu (podszywanie)."""
    return rule_res.score_bonus - (rule_res.known_bonus if risk != "low" else 0)


def _final_importance(analysis_importance: int, rule_res, assessment, threshold: int) -> int:
    """Ważność końcowa: model + premie z reguł.

    VIP nie spada poniżej progu, ale TYLKO gdy mail nie ma żadnego sygnału phishingu: nadawca
    „Szef <szef@firma.pl>” bywa podrobiony, a ocena ryzyka może uznać wyłudzenie za „low”.
    """
    value = max(0, min(10, analysis_importance + _rule_bonus(rule_res, assessment.risk)))
    if rule_res.force_important and assessment.risk == "low" and not assessment.reasons:
        value = max(value, threshold)
    return value


def run_cycle(deps: PipelineDeps, check_backlog: bool = False) -> CycleResult:
    """Wykonuje pojedynczy cyklu sprawdzania poczty dla wszystkich skonfigurowanych kont.

    Dla każdego konta i folderu:
    1. Jeśli pierwsze uruchomienie lub check_backlog=True: pobiera i analizuje zaległości (backlog).
       Ważne zaległe trafiają do backlog_important (bez natychmiastowego mark_seen).
    2. Pobiera nowe wiadomości przez fetch_new.
    3. Ocenia regułami rules.evaluate (zablokowane od razu mark_seen).
    4. Analizuje przez Ollama LLM z failoverem.
    5. Oblicza łączną ważność (importance + bonus reguł, clamp 0-10).
    6. Zapisuje mark_seen i aktualizuje last_uid przez commit_progress.
    Awaria Ollamy dla jednego maila nie przerywa cyklu ani nie gubi maila.
    """
    result = CycleResult()
    known_contacts = (
        list(deps.config.vip_senders)
        + [r.sender for r in deps.config.vip_rules if r.sender]
        + deps.store.get_all_contact_addresses()
    )
    my_addresses = [acc.username for acc in deps.config.accounts if acc.username]

    for account in deps.config.accounts:
        try:
            client = deps.client_factory(account)
        except Exception as exc:
            result.errors.append(f"Nie udało się połączyć z kontem '{account.name}': {exc}")
            continue

        # Pobieramy Message-ID z folderu wysłanych do reguł
        sent_ids: frozenset[str] = frozenset()
        sent_folder_err: str | None = None
        if account.sent_folder:
            try:
                sent_ids = fetch_sent_message_ids(
                    client, account.sent_folder, days=deps.config.backlog_days
                )
            except Exception as exc:
                sent_folder_err = format_friendly_error(exc, deps.config.language)
                result.errors.append(sent_folder_err)

        # Indeksujemy wysłane wiadomości (direction='out', importance=0, bez LLM)
        try:
            sent_items = fetch_sent_for_index(
                client,
                deps.store,
                account.name,
                sent_folder=account.sent_folder,
                days=deps.config.backlog_days,
            )
            for s_uid, s_mail in sent_items:
                _index_mail(
                    deps.store,
                    account.name,
                    sent_items.folder,
                    sent_items.uidvalidity,
                    s_uid,
                    s_mail,
                    importance=0,
                    why="",
                    summary="",
                    direction="out",
                )
        except Exception as exc:
            err_msg = format_friendly_error(exc, deps.config.language)
            if err_msg != sent_folder_err:
                result.errors.append(err_msg)

        known_addresses, known_domains = deps.store.get_correspondents(
            exclude={a.lower() for a in my_addresses}
        )
        rules = Rules(
            known_addresses=known_addresses,
            known_domains=known_domains,
            auto_vip=deps.config.auto_vip,
            vip_senders=tuple(deps.config.vip_senders),
            vip_rules=tuple(deps.config.vip_rules),
            keywords=tuple(deps.config.keywords),
            blocked_senders=tuple(deps.config.blocked_senders),
            ignore_rules=tuple(deps.config.ignore_rules),
            sent_message_ids=sent_ids,
        )

        for folder in account.folders:
            try:
                uidvalidity = client.get_uidvalidity(folder)
            except Exception as exc:
                result.errors.append(
                    f"Błąd pobierania UIDVALIDITY dla '{account.name}/{folder}': {exc}"
                )
                continue

            last_uid = deps.store.get_last_uid(account.name, folder, uidvalidity)
            is_first_run = not deps.store.has_last_uid(account.name, folder, uidvalidity)
            backlog_ok = True
            baseline = 0
            if is_first_run:
                # Pierwsze uruchomienie: cała dotychczasowa historia NIE jest "nowa" -- obsługuje ją
                # tylko tryb zaległych (UNSEEN). Zapamiętujemy najwyższy UID jako linię bazową.
                try:
                    baseline = max(client.get_uids_greater_than(folder, 0), default=0)
                except Exception as exc:
                    result.errors.append(
                        f"Błąd ustalania linii bazowej dla '{account.name}/{folder}': {exc}"
                    )
                    continue

            # 1. Obsługa zaległości (Backlog)
            if is_first_run or check_backlog:
                try:
                    backlog_items = fetch_backlog(
                        client, deps.store, account.name, folder, days=deps.config.backlog_days
                    )
                except Exception as exc:
                    result.errors.append(
                        f"Błąd pobierania zaległości dla '{account.name}/{folder}': {exc}"
                    )
                    backlog_items = []
                    backlog_ok = False

                for uid, mail in backlog_items:
                    rule_info = MailInfo(
                        sender=mail.sender,
                        subject=mail.subject,
                        body=mail.body_text,
                        in_reply_to=mail.in_reply_to,
                        references=mail.references,
                    )
                    rule_res = rules_evaluate(rule_info, rules)

                    if rule_res.blocked:
                        deps.store.mark_seen(
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail.message_id,
                            status="analyzed",
                            importance=0,
                        )
                        _index_mail(
                            deps.store,
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail,
                            importance=0,
                            why="; ".join(rule_res.reasons) or "Zablokowany nadawca",
                        )
                        continue

                    # Ocena ryzyka bezpieczeństwa i phishingu
                    risk_assessment = phishing_assess(
                        mail=mail,
                        headers=None,
                        my_addresses=my_addresses,
                        known_contacts=known_contacts,
                    )
                    is_high_risk = risk_assessment.risk == "high"
                    is_medium_risk = risk_assessment.risk == "medium"
                    reasons_text = "; ".join(risk_assessment.reasons)

                    if is_high_risk:
                        auto_summary = (
                            "⚠ Podejrzana wiadomość (wykryto ryzyko phishingu/zagrożenia). "
                            f"Powody: {reasons_text}. "
                            "Nie klikaj w linki ani nie otwieraj załączników."
                        )
                        final_importance = min(3, _rule_bonus(rule_res, risk_assessment.risk))
                        processed = ProcessedMail(
                            account=account.name,
                            folder=folder,
                            uidvalidity=uidvalidity,
                            uid=uid,
                            mail=mail,
                            final_importance=final_importance,
                            rule_reasons=rule_res.reasons,
                            analysis_reason=auto_summary,
                            action="ignore",
                            language=(
                                deps.config.language
                                if deps.config.language in ("pl", "en")
                                else "other"
                            ),
                            suspicious=True,
                            risk_level="high",
                            risk_reasons=risk_assessment.reasons,
                            summary=auto_summary,
                        )
                        deps.store.mark_seen(
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail.message_id,
                            status="analyzed",
                            importance=final_importance,
                        )
                        _index_mail(
                            deps.store,
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail,
                            importance=final_importance,
                            why=auto_summary,
                            summary=auto_summary,
                            direction="in",
                            risk="high",
                            risk_reasons=reasons_text,
                        )
                        result.suspicious.append(processed)
                        continue

                    messages = build_messages(
                        deps.config.analysis_prompt,
                        mail.sender,
                        mail.subject,
                        mail.body_text,
                        rule_res.reasons,
                    )
                    lang = deps.config.language if deps.config.language in ("pl", "en") else "other"
                    model = pick_model(lang, deps.config.ollama)

                    try:
                        analysis = deps.ollama_client.classify(messages, model)
                        deps.store.clear_attempts(account.name, folder, uidvalidity, uid)
                    except AnalyzerTransportError as exc:
                        result.errors.append(
                            f"Błąd połączenia z Ollama dla zaległego maila UID {uid} "
                            f"w '{account.name}/{folder}': {exc}"
                        )
                        backlog_ok = False
                        break
                    except AnalyzerFormatError as exc:
                        attempts = deps.store.increment_attempts(
                            account.name, folder, uidvalidity, uid
                        )
                        result.errors.append(
                            f"Błąd formatu dla zaległego maila UID {uid} "
                            f"w '{account.name}/{folder}' (próba {attempts}/3): {exc}"
                        )
                        if attempts >= 3:
                            deps.store.mark_seen(
                                account.name,
                                folder,
                                uidvalidity,
                                uid,
                                mail.message_id,
                                status="failed",
                                importance=0,
                            )
                            deps.store.clear_attempts(account.name, folder, uidvalidity, uid)
                        else:
                            backlog_ok = False
                        continue
                    except AnalyzerError as exc:
                        result.errors.append(
                            f"Błąd analizy zaległego maila UID {uid} "
                            f"w '{account.name}/{folder}': {exc}"
                        )
                        continue

                    final_importance = _final_importance(
                        analysis.importance,
                        rule_res,
                        risk_assessment,
                        deps.config.importance_threshold,
                    )
                    analysis_reason = analysis.reason
                    summary = ""
                    if is_medium_risk:
                        analysis_reason = (
                            f"[Uwaga: wiadomość może być podejrzana] {analysis.reason}"
                        )
                        summary = f"[Uwaga: wiadomość może być podejrzana] {analysis.reason}"

                    processed = ProcessedMail(
                        account=account.name,
                        folder=folder,
                        uidvalidity=uidvalidity,
                        uid=uid,
                        mail=mail,
                        final_importance=final_importance,
                        rule_reasons=rule_res.reasons,
                        analysis_reason=analysis_reason,
                        action=analysis.action,
                        language=analysis.language,
                        suspicious=is_medium_risk,
                        risk_level=risk_assessment.risk,
                        risk_reasons=risk_assessment.reasons,
                        summary=summary,
                    )

                    if final_importance >= deps.config.importance_threshold:
                        # Ważne zaległe zapisujemy jako backlog_pending
                        deps.store.mark_seen(
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail.message_id,
                            status="backlog_pending",
                            importance=final_importance,
                        )
                        result.backlog_important.append(processed)
                    else:
                        # Nieważne oznaczamy jako seen, aby nie analizować ich ponownie
                        deps.store.mark_seen(
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail.message_id,
                            status="analyzed",
                            importance=final_importance,
                        )

                    _index_mail(
                        deps.store,
                        account.name,
                        folder,
                        uidvalidity,
                        uid,
                        mail,
                        importance=final_importance,
                        why=analysis_reason,
                        summary=summary,
                        direction="in",
                        risk=risk_assessment.risk,
                        risk_reasons=reasons_text,
                    )

            if is_first_run:
                if not backlog_ok:
                    continue  # ponowimy w następnym cyklu
                commit_progress(deps.store, account.name, folder, uidvalidity, baseline)
                last_uid = baseline

            # 2. Pobieranie i analiza nowych wiadomości
            try:
                new_items = fetch_new(client, deps.store, account.name, folder)
            except Exception as exc:
                result.errors.append(
                    f"Błąd pobierania nowych wiadomości dla '{account.name}/{folder}': {exc}"
                )
                continue

            last_committed_uid = last_uid

            for uid, mail in new_items:
                rule_info = MailInfo(
                    sender=mail.sender,
                    subject=mail.subject,
                    body=mail.body_text,
                    in_reply_to=mail.in_reply_to,
                    references=mail.references,
                )
                rule_res = rules_evaluate(rule_info, rules)

                if rule_res.blocked:
                    deps.store.mark_seen(
                        account.name,
                        folder,
                        uidvalidity,
                        uid,
                        mail.message_id,
                        status="analyzed",
                        importance=0,
                    )
                    _index_mail(
                        deps.store,
                        account.name,
                        folder,
                        uidvalidity,
                        uid,
                        mail,
                        importance=0,
                        why="; ".join(rule_res.reasons) or "Zablokowany nadawca",
                    )
                    last_committed_uid = max(last_committed_uid, uid)
                    continue

                # Ocena ryzyka bezpieczeństwa i phishingu
                risk_assessment = phishing_assess(
                    mail=mail,
                    headers=None,
                    my_addresses=my_addresses,
                    known_contacts=known_contacts,
                )
                is_high_risk = risk_assessment.risk == "high"
                is_medium_risk = risk_assessment.risk == "medium"
                reasons_text = "; ".join(risk_assessment.reasons)

                if is_high_risk:
                    auto_summary = (
                        "⚠ Podejrzana wiadomość (wykryto ryzyko phishingu/zagrożenia). "
                        f"Powody: {reasons_text}. "
                        "Nie klikaj w linki ani nie otwieraj załączników."
                    )
                    final_importance = min(3, _rule_bonus(rule_res, risk_assessment.risk))
                    processed = ProcessedMail(
                        account=account.name,
                        folder=folder,
                        uidvalidity=uidvalidity,
                        uid=uid,
                        mail=mail,
                        final_importance=final_importance,
                        rule_reasons=rule_res.reasons,
                        analysis_reason=auto_summary,
                        action="ignore",
                        language=(
                            deps.config.language
                            if deps.config.language in ("pl", "en")
                            else "other"
                        ),
                        suspicious=True,
                        risk_level="high",
                        risk_reasons=risk_assessment.reasons,
                        summary=auto_summary,
                    )
                    deps.store.mark_seen(
                        account.name,
                        folder,
                        uidvalidity,
                        uid,
                        mail.message_id,
                        status="analyzed",
                        importance=final_importance,
                    )
                    last_committed_uid = max(last_committed_uid, uid)
                    _index_mail(
                        deps.store,
                        account.name,
                        folder,
                        uidvalidity,
                        uid,
                        mail,
                        importance=final_importance,
                        why=auto_summary,
                        summary=auto_summary,
                        direction="in",
                        risk="high",
                        risk_reasons=reasons_text,
                    )
                    result.suspicious.append(processed)
                    continue

                messages = build_messages(
                    deps.config.analysis_prompt,
                    mail.sender,
                    mail.subject,
                    mail.body_text,
                    rule_res.reasons,
                )
                lang = deps.config.language if deps.config.language in ("pl", "en") else "other"
                model = pick_model(lang, deps.config.ollama)

                try:
                    analysis = deps.ollama_client.classify(messages, model)
                    deps.store.clear_attempts(account.name, folder, uidvalidity, uid)
                except AnalyzerTransportError as exc:
                    result.errors.append(
                        f"Błąd połączenia z Ollama dla UID {uid} w '{account.name}/{folder}': {exc}"
                    )
                    # Błąd transportu: oba endpointy padły, przerywamy folder
                    break
                except AnalyzerFormatError as exc:
                    attempts = deps.store.increment_attempts(account.name, folder, uidvalidity, uid)
                    result.errors.append(
                        f"Błąd formatu odpowiedzi Ollama dla UID {uid} "
                        f"w '{account.name}/{folder}' (próba {attempts}/3): {exc}"
                    )
                    if attempts >= 3:
                        deps.store.mark_seen(
                            account.name,
                            folder,
                            uidvalidity,
                            uid,
                            mail.message_id,
                            status="failed",
                            importance=0,
                        )
                        deps.store.clear_attempts(account.name, folder, uidvalidity, uid)
                        last_committed_uid = max(last_committed_uid, uid)
                        continue
                    # Jeśli < 3 próby: nie przesuwamy wskaźnika za ten UID i ponowimy
                    break
                except AnalyzerError as exc:
                    result.errors.append(
                        f"Błąd analizy nowego maila UID {uid} w '{account.name}/{folder}': {exc}"
                    )
                    break

                final_importance = _final_importance(
                    analysis.importance,
                    rule_res,
                    risk_assessment,
                    deps.config.importance_threshold,
                )
                deps.store.mark_seen(
                    account.name,
                    folder,
                    uidvalidity,
                    uid,
                    mail.message_id,
                    status="analyzed",
                    importance=final_importance,
                )
                last_committed_uid = max(last_committed_uid, uid)

                analysis_reason = analysis.reason
                summary = ""
                if is_medium_risk:
                    analysis_reason = f"[Uwaga: wiadomość może być podejrzana] {analysis.reason}"
                    summary = f"[Uwaga: wiadomość może być podejrzana] {analysis.reason}"

                processed = ProcessedMail(
                    account=account.name,
                    folder=folder,
                    uidvalidity=uidvalidity,
                    uid=uid,
                    mail=mail,
                    final_importance=final_importance,
                    rule_reasons=rule_res.reasons,
                    analysis_reason=analysis_reason,
                    action=analysis.action,
                    language=analysis.language,
                    suspicious=is_medium_risk,
                    risk_level=risk_assessment.risk,
                    risk_reasons=risk_assessment.reasons,
                    summary=summary,
                )

                _index_mail(
                    deps.store,
                    account.name,
                    folder,
                    uidvalidity,
                    uid,
                    mail,
                    importance=final_importance,
                    why=analysis_reason,
                    summary=summary,
                    direction="in",
                    risk=risk_assessment.risk,
                    risk_reasons=reasons_text,
                )

                if final_importance >= deps.config.importance_threshold:
                    result.important.append(processed)

            # Aktualizujemy last_uid na końcu przetwarzania folderu
            if last_committed_uid > last_uid:
                commit_progress(deps.store, account.name, folder, uidvalidity, last_committed_uid)

    deps.store.purge_older_than(deps.config.index_retention_days)
    return result
