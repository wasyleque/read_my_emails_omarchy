"""Moduł podsumowania wątków i tematów (topic digest)."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Literal

from mailvoice.core.analyzer import AnalyzerError, OllamaClient, pick_model
from mailvoice.core.config import AppConfig
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.core.threading import clean_subject

TopicStatus = Literal["oczekuje_na_mnie", "oczekuje_na_innych", "zamknięte", "informacyjne"]

TOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "why": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["oczekuje_na_mnie", "oczekuje_na_innych", "zamknięte", "informacyjne"],
        },
        "who_to_whom": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["title", "why", "status", "who_to_whom"],
}

_STATUS_PRIORITY: dict[str, int] = {
    "oczekuje_na_mnie": 0,
    "oczekuje_na_innych": 1,
    "informacyjne": 2,
    "zamknięte": 3,
}


@dataclass(frozen=True)
class Participant:
    address: str
    role: str  # 'from' | 'to' | 'cc'
    count: int


@dataclass(frozen=True)
class Topic:
    title: str
    participants: list[Participant]
    who_to_whom: list[str]
    why: str
    status: TopicStatus
    last_activity: datetime
    importance: int
    mail_count: int


@dataclass(frozen=True)
class Digest:
    period: str
    topics: list[Topic]


def _clean_addr(raw: str) -> str:
    """Wyciąga i normalizuje sam adres e-mail."""
    _, addr = parseaddr(raw)
    return addr.strip().lower() if addr else raw.strip().lower()


def _parse_iso_date(date_str: str | None) -> datetime:
    """Parsuje ciąg ISO 8601 do datetime ze strefą UTC."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _detect_language(records: list[MailIndexRecord]) -> str:
    """Wykrywa, czy w treści metadanych dominuje język polski."""
    pl_chars = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    for r in records:
        text = f"{r.subject} {r.why or ''} {r.summary or ''}"
        if any(c in pl_chars for c in text):
            return "pl"
    return "en"


def _extract_participants(records: list[MailIndexRecord]) -> list[Participant]:
    """Wyciąga uczestników z listy wiadomości wraz z ich rolą i liczbą wystąpień."""
    from_counts: Counter[str] = Counter()
    to_counts: Counter[str] = Counter()
    cc_counts: Counter[str] = Counter()

    for r in records:
        sender_addr = _clean_addr(r.sender)
        if sender_addr:
            from_counts[sender_addr] += 1

        # recipients to lista rozdzielona przecinkami
        if r.recipients:
            for recipient in r.recipients.split(","):
                rec_addr = _clean_addr(recipient)
                if rec_addr and rec_addr != sender_addr:
                    to_counts[rec_addr] += 1

    all_addrs = set(from_counts.keys()) | set(to_counts.keys()) | set(cc_counts.keys())
    participants: list[Participant] = []

    for addr in sorted(all_addrs):
        if from_counts[addr] > 0:
            role = "from"
            count = from_counts[addr] + to_counts[addr] + cc_counts[addr]
        elif to_counts[addr] > 0:
            role = "to"
            count = to_counts[addr] + cc_counts[addr]
        else:
            role = "cc"
            count = cc_counts[addr]
        participants.append(Participant(address=addr, role=role, count=count))

    return participants


def _determine_status(
    raw_status: str,
    last_sender: str,
    user_addrs: set[str],
    thread_records: list[MailIndexRecord],
) -> TopicStatus:
    """Weryfikuje i dostosowuje status wątku w oparciu o dane wątku i ostatnią wiadomość."""
    if raw_status in ("zamknięte", "informacyjne"):
        return raw_status  # type: ignore[return-value]

    if thread_records:
        last_rec = thread_records[-1]
        direction = getattr(last_rec, "direction", "in")
        if direction == "out":
            return "oczekuje_na_innych"
        # Fallback po adresach użytkownika dla starszych rekordów bez kierunku lub z innych kont
        if user_addrs and _clean_addr(last_rec.sender) in user_addrs:
            return "oczekuje_na_innych"
        return "oczekuje_na_mnie"

    last_sender_clean = _clean_addr(last_sender)
    if user_addrs and last_sender_clean in user_addrs:
        return "oczekuje_na_innych"

    return "oczekuje_na_mnie"


def _fallback_who_to_whom(records: list[MailIndexRecord]) -> list[str]:
    """Generuje listę relacji kto-do-kogo bez użycia LLM."""
    lines: list[str] = []
    for r in records[-4:]:
        subj = clean_subject(r.subject)
        direction = getattr(r, "direction", "in")
        if direction == "out":
            recips = (
                ", ".join(_clean_addr(a) for a in r.recipients.split(",") if _clean_addr(a))
                or "odbiorca"
            )
            lines.append(f"Ty -> {recips}: {subj}" if subj else f"Ty -> {recips}")
        else:
            sender = _clean_addr(r.sender) or r.sender or "nadawca"
            lines.append(f"{sender} -> Ty: {subj}" if subj else f"{sender} -> Ty")
    return lines


def build_digest(
    store: Store,
    client: OllamaClient,
    config: AppConfig,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> Digest:
    """Buduje podsumowanie tematów (Digest) z wybranego okresu na podstawie indeksu wiadomości."""
    now = datetime.now(timezone.utc)

    # 1. Ustalenie zakresu dat
    if since is None:
        since_dt = now - timedelta(days=config.digest_days)
        since_iso = since_dt.isoformat()
        period_label = f"ostatnie {config.digest_days} dni"
    elif isinstance(since, datetime):
        since_iso = since.isoformat()
        period_label = f"od {since.strftime('%Y-%m-%d')}"
    else:
        since_iso = since
        period_label = f"od {since[:10]}"

    if until is None:
        until_iso = now.isoformat()
    elif isinstance(until, datetime):
        until_iso = until.isoformat()
        period_label += f" do {until.strftime('%Y-%m-%d')}"
    else:
        until_iso = until
        period_label += f" do {until[:10]}"

    # Adresy użytkownika (do ustalenia kierunku 'na kogo czeka')
    user_addrs = set()
    for acc in config.accounts:
        if getattr(acc, "username", None):
            user_addrs.add(acc.username.strip().lower())
        if getattr(acc, "email", None):
            user_addrs.add(acc.email.strip().lower())
    for addr in config.my_addresses:
        if addr:
            user_addrs.add(addr.strip().lower())

    # 2. Pobranie wiadomości z indeksu
    records = store.get_all_indexed_records(since=since_iso, until=until_iso)
    if not records:
        return Digest(period=period_label, topics=[])

    # 3. Pogrupowanie po thread_key
    thread_keys_in_range: list[str] = []
    seen_threads: set[str] = set()
    for r in records:
        if r.thread_key not in seen_threads:
            seen_threads.add(r.thread_key)
            thread_keys_in_range.append(r.thread_key)

    topics: list[Topic] = []

    for t_key in thread_keys_in_range:
        # Pobieramy wszystkie wiadomości z wątku do daty `until` dla pełnego kontekstu
        all_thread_records = store.get_records_for_thread(t_key)
        thread_records = [r for r in all_thread_records if not r.date or r.date <= until_iso]
        if not thread_records:
            continue

        thread_records.sort(key=lambda r: r.date or "")
        last_record = thread_records[-1]
        last_mail_date = last_record.date
        mail_count = len(thread_records)
        last_activity = _parse_iso_date(last_mail_date)
        importance = max((r.importance or 0 for r in thread_records), default=0)
        participants = _extract_participants(thread_records)

        # 4. Sprawdzenie pamięci podręcznej (cache w SQLite)
        cached = store.get_topic_digest_cache(t_key)
        if (
            cached is not None
            and cached.last_mail_date == last_mail_date
            and cached.mail_count == mail_count
        ):
            # Używamy danych z cache
            final_status = _determine_status(
                cached.status, last_record.sender, user_addrs, thread_records
            )
            topics.append(
                Topic(
                    title=cached.title,
                    participants=participants,
                    who_to_whom=cached.who_to_whom,
                    why=cached.why,
                    status=final_status,
                    last_activity=last_activity,
                    importance=importance,
                    mail_count=mail_count,
                )
            )
            continue

        # 5. Przygotowanie zapytania do LLM
        lang = _detect_language(thread_records)
        model = pick_model(lang, config.ollama)

        summary_lines: list[str] = []
        for r in thread_records:
            direction = getattr(r, "direction", "in")
            dt_str = r.date[:16].replace("T", " ") if r.date else ""
            summary_content = r.summary or r.why or clean_subject(r.subject)
            if direction == "out":
                recips = (
                    ", ".join(_clean_addr(a) for a in r.recipients.split(",") if _clean_addr(a))
                    or r.recipients
                )
                summary_lines.append(
                    f"- [{dt_str}] (Wychodząca) Ty -> {recips}\n"
                    f"  Temat: {r.subject}\n"
                    f"  Treść/streszczenie: {summary_content}"
                )
            else:
                sender = _clean_addr(r.sender) or r.sender
                summary_lines.append(
                    f"- [{dt_str}] (Przychodząca) {sender} -> Ty\n"
                    f"  Temat: {r.subject}\n"
                    f"  Streszczenie: {summary_content}"
                )

        last_dir = getattr(last_record, "direction", "in")
        user_content = (
            f"Adresy kont użytkownika: {', '.join(sorted(user_addrs))}\n"
            f"Ostatni nadawca w wątku: {last_record.sender} (kierunek: {last_dir})\n\n"
            f"Wiadomości w wątku:\n" + "\n".join(summary_lines)
        )

        system_prompt = (
            "Jesteś asystentem poczty elektronicznej. Na podstawie historii metadanych "
            "i streszczeń wiadomości z wątku przygotuj zwięzłe podsumowanie tematu "
            "w formacie JSON.\n"
            "Wymagania pól JSON:\n"
            "- title: krótki, zwięzły tytuł tematu/sprawy (max 1 zdanie)\n"
            "- why: cel i powód korespondencji (1-2 krótkie zdania)\n"
            "- status: 'oczekuje_na_mnie', 'oczekuje_na_innych', 'zamknięte' lub 'informacyjne'\n"
            "- who_to_whom: lista podsumowująca kto do kogo pisał "
            "(np. 'Anna -> Ty: oferta', 'Ty -> Anna: akceptacja')\n"
            "Maksymalnie 4 zdania łącznie. Zwróć tylko JSON zgodny ze schematem."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        title = clean_subject(last_record.subject) or "Temat korespondencji"
        why = last_record.why or last_record.summary or "Wątek wiadomości."
        if getattr(last_record, "direction", "in") == "out":
            status_cand = "oczekuje_na_innych"
        elif user_addrs and _clean_addr(last_record.sender) in user_addrs:
            status_cand = "oczekuje_na_innych"
        else:
            status_cand = "oczekuje_na_mnie"
        who_to_whom = _fallback_who_to_whom(thread_records)

        try:
            res = client.chat_json(messages, model, TOPIC_SCHEMA)
            if isinstance(res, dict):
                title = str(res.get("title") or title).strip()
                why = str(res.get("why") or why).strip()
                status_cand = str(res.get("status") or status_cand).strip()
                parsed_w2w = res.get("who_to_whom")
                if isinstance(parsed_w2w, list) and parsed_w2w:
                    who_to_whom = [str(item).strip() for item in parsed_w2w if str(item).strip()]

                # Zapis do pamięci podręcznej po udanym wywołaniu LLM
                store.save_topic_digest_cache(
                    thread_key=t_key,
                    last_mail_date=last_mail_date,
                    mail_count=mail_count,
                    title=title,
                    why=why,
                    status=status_cand,
                    who_to_whom=who_to_whom,
                )
        except (AnalyzerError, Exception):
            # Błąd LLM dla jednego tematu nie zabija reszty
            pass

        final_status = _determine_status(
            status_cand, last_record.sender, user_addrs, thread_records
        )

        topics.append(
            Topic(
                title=title,
                participants=participants,
                who_to_whom=who_to_whom,
                why=why,
                status=final_status,
                last_activity=last_activity,
                importance=importance,
                mail_count=mail_count,
            )
        )

    # 6. Sortowanie: najpierw oczekuje_na_mnie, potem wg ważności, potem najświeższe
    topics.sort(
        key=lambda t: (
            _STATUS_PRIORITY.get(t.status, 99),
            -t.importance,
            -t.last_activity.timestamp(),
        )
    )

    return Digest(period=period_label, topics=topics)
