"""Moduł potoku przetwarzania poczty (pipeline) - czysta logika bez Qt i audio."""

from dataclasses import dataclass, field
from typing import Callable, Sequence

from mailvoice.core.analyzer import AnalyzerError, OllamaClient, build_messages, pick_model
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.imap_fetch import (
    MailboxClient,
    commit_progress,
    fetch_backlog,
    fetch_new,
    fetch_sent_message_ids,
)
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.rules import MailInfo, Rules
from mailvoice.core.rules import evaluate as rules_evaluate
from mailvoice.core.store import Store


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


@dataclass
class CycleResult:
    """Wynik wykonania cyklu sprawdzania poczty."""

    important: list[ProcessedMail] = field(default_factory=list)
    backlog_important: list[ProcessedMail] = field(default_factory=list)
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


def resolve_backlog(store: Store, items: Sequence[ProcessedMail], accepted: bool) -> None:
    """Oznacza zaległe wiadomości w bazie store w zależności od decyzji użytkownika.

    accepted=True -> status 'analyzed'
    accepted=False -> status 'backlog_declined'
    """
    status = "analyzed" if accepted else "backlog_declined"
    for item in items:
        store.mark_seen(
            account=item.account,
            folder=item.folder,
            uidvalidity=item.uidvalidity,
            uid=item.uid,
            message_id=item.mail.message_id,
            status=status,
            importance=item.final_importance,
        )


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

    for account in deps.config.accounts:
        try:
            client = deps.client_factory(account)
        except Exception as exc:
            result.errors.append(f"Nie udało się połączyć z kontem '{account.name}': {exc}")
            continue

        # Pobieramy Message-ID z folderu wysłanych do reguł
        sent_ids: frozenset[str] = frozenset()
        if account.sent_folder:
            try:
                sent_ids = fetch_sent_message_ids(
                    client, account.sent_folder, days=deps.config.backlog_days
                )
            except Exception as exc:
                result.errors.append(
                    f"Błąd pobierania wysłanych wiadomości z '{account.sent_folder}': {exc}"
                )

        rules = Rules(
            vip_senders=tuple(deps.config.vip_senders),
            keywords=tuple(deps.config.keywords),
            blocked_senders=tuple(deps.config.blocked_senders),
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
                    except AnalyzerError as exc:
                        result.errors.append(
                            f"Błąd analizy zaległego maila UID {uid} "
                            f"w '{account.name}/{folder}': {exc}"
                        )
                        continue

                    final_importance = max(0, min(10, analysis.importance + rule_res.score_bonus))
                    processed = ProcessedMail(
                        account=account.name,
                        folder=folder,
                        uidvalidity=uidvalidity,
                        uid=uid,
                        mail=mail,
                        final_importance=final_importance,
                        rule_reasons=rule_res.reasons,
                        analysis_reason=analysis.reason,
                        action=analysis.action,
                        language=analysis.language,
                    )

                    if final_importance >= deps.config.importance_threshold:
                        # Ważne zaległe NIE są oznaczane jako seen, dopóki użytkownik nie zdecyduje
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
                    last_committed_uid = max(last_committed_uid, uid)
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
                except AnalyzerError as exc:
                    result.errors.append(
                        f"Błąd analizy nowego maila UID {uid} w '{account.name}/{folder}': {exc}"
                    )
                    # Nie oznaczamy jako seen ani nie przesuwamy wskaźnika za ten UID
                    break

                final_importance = max(0, min(10, analysis.importance + rule_res.score_bonus))
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

                processed = ProcessedMail(
                    account=account.name,
                    folder=folder,
                    uidvalidity=uidvalidity,
                    uid=uid,
                    mail=mail,
                    final_importance=final_importance,
                    rule_reasons=rule_res.reasons,
                    analysis_reason=analysis.reason,
                    action=analysis.action,
                    language=analysis.language,
                )

                if final_importance >= deps.config.importance_threshold:
                    result.important.append(processed)

            # Aktualizujemy last_uid na końcu przetwarzania folderu
            if last_committed_uid > last_uid:
                commit_progress(deps.store, account.name, folder, uidvalidity, last_committed_uid)

    return result
