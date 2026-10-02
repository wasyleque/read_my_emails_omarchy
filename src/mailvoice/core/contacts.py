"""Moduł kart kontaktów (contacts) i kontekstu nadawców."""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr

from mailvoice.core.analyzer import AnalyzerError, OllamaClient, pick_model
from mailvoice.core.config import AppConfig
from mailvoice.core.digest import Topic, _parse_iso_date
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.core.threading import clean_subject


@dataclass(frozen=True)
class Contact:
    """Reprezentacja kontaktu w książce adresowej."""

    id: int | None
    display_name: str
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class ContactCard:
    """Karta kontekstu kontaktu ze sprawami, wymianami i wskazówkami relacji."""

    name: str
    addresses: tuple[str, ...]
    first_seen: datetime | None
    last_contact: datetime | None
    mail_count: int
    topics: list[Topic]
    open_items: list[str]
    last_exchange: list[tuple[str, str, str]]
    relationship_hint: str
    why_it_matters: str


CONTACT_HINT_SCHEMA = {
    "type": "object",
    "properties": {
        "relationship_hint": {"type": "string"},
        "why_it_matters": {"type": "string"},
    },
    "required": ["relationship_hint", "why_it_matters"],
}


def _clean_email(raw: str) -> str:
    """Zwraca znormalizowany adres e-mail (małe litery)."""
    _, addr = parseaddr(raw)
    return addr.strip().lower() if addr else raw.strip().lower()


def _extract_display_name(raw: str) -> str:
    """Wyciąga nazwę wyświetlaną nadawcy (np. 'Jan Kowalski')."""
    name, _ = parseaddr(raw)
    return name.strip()


def _get_domain(addr: str) -> str:
    """Zwraca domenę adresu e-mail."""
    return addr.split("@")[-1].lower() if "@" in addr else ""


def resolve_contact(store: Store, address_or_name: str) -> Contact | None:
    """Rozpoznaje kontakt po adresie e-mail lub nazwie; uczy się z mail_index."""
    query = address_or_name.strip()
    if not query:
        return None

    clean_addr = _clean_email(query)
    cur = store.connection.cursor()

    # 1. Sprawdzenie w tabeli contacts i contact_addresses po adresie
    cur.execute(
        """
        SELECT c.id, c.display_name
        FROM contacts c
        JOIN contact_addresses ca ON c.id = ca.contact_id
        WHERE ca.address = ?
        """,
        (clean_addr,),
    )
    row = cur.fetchone()

    # 2. Sprawdzenie po nazwie
    if not row:
        cur.execute(
            """
            SELECT id, display_name FROM contacts
            WHERE LOWER(display_name) = ?
            """,
            (query.lower(),),
        )
        row = cur.fetchone()

    if row:
        c_id, disp_name = row[0], row[1]
        cur.execute(
            "SELECT address FROM contact_addresses WHERE contact_id = ? ORDER BY address",
            (c_id,),
        )
        addrs = tuple(r[0] for r in cur.fetchall())
        return Contact(id=c_id, display_name=disp_name, addresses=addrs)

    # 3. Jeśli brak w tabeli kontaktów, przeszukaj indeks wiadomości mail_index
    cur.execute(
        """
        SELECT sender, recipients FROM mail_index
        WHERE sender LIKE ? OR recipients LIKE ? OR sender LIKE ? OR recipients LIKE ?
        """,
        (f"%{clean_addr}%", f"%{clean_addr}%", f"%{query}%", f"%{query}%"),
    )
    matches = cur.fetchall()
    if not matches:
        return None

    # Zbieramy nazwy i powiązane adresy
    display_names: list[str] = []
    found_addresses: set[str] = set()

    if "@" in clean_addr:
        found_addresses.add(clean_addr)

    for sender_raw, recipients_raw in matches:
        s_name = _extract_display_name(sender_raw)
        s_addr = _clean_email(sender_raw)
        if clean_addr and s_addr == clean_addr:
            if s_name:
                display_names.append(s_name)
        elif query.lower() in s_name.lower():
            if s_name:
                display_names.append(s_name)
            if s_addr:
                found_addresses.add(s_addr)

        for rec in recipients_raw.split(","):
            r_name = _extract_display_name(rec)
            r_addr = _clean_email(rec)
            if clean_addr and r_addr == clean_addr:
                if r_name:
                    display_names.append(r_name)
                found_addresses.add(r_addr)
            elif query.lower() in r_name.lower():
                if r_name:
                    display_names.append(r_name)
                if r_addr:
                    found_addresses.add(r_addr)

    if not found_addresses and clean_addr:
        found_addresses.add(clean_addr)

    if not found_addresses:
        return None

    # Ustalenie nazwy wyświetlanej
    chosen_name = (
        max(set(display_names), key=display_names.count)
        if display_names
        else (clean_addr.split("@")[0].replace(".", " ").title() if "@" in clean_addr else query)
    )

    # Zachowawcze scalanie: czy istnieje już kontakt o tej samej nazwie i domenie?
    first_addr = next(iter(found_addresses))
    domain = _get_domain(first_addr)
    cur.execute(
        """
        SELECT c.id, c.display_name, ca.address
        FROM contacts c
        JOIN contact_addresses ca ON c.id = ca.contact_id
        WHERE LOWER(c.display_name) = ?
        """,
        (chosen_name.lower(),),
    )
    existing_rows = cur.fetchall()
    target_id: int | None = None
    for ex_id, ex_name, ex_addr in existing_rows:
        if domain and _get_domain(ex_addr) == domain:
            target_id = ex_id
            break

    if target_id is not None:
        for addr in found_addresses:
            cur.execute(
                "INSERT OR IGNORE INTO contact_addresses (contact_id, address) VALUES (?, ?)",
                (target_id, addr),
            )
        store.connection.commit()
        cur.execute(
            "SELECT address FROM contact_addresses WHERE contact_id = ? ORDER BY address",
            (target_id,),
        )
        all_addrs = tuple(r[0] for r in cur.fetchall())
        return Contact(id=target_id, display_name=chosen_name, addresses=all_addrs)

    # Utworzenie nowego kontaktu
    cur.execute("INSERT INTO contacts (display_name) VALUES (?)", (chosen_name,))
    new_id = cur.lastrowid
    for addr in found_addresses:
        cur.execute(
            "INSERT OR IGNORE INTO contact_addresses (contact_id, address) VALUES (?, ?)",
            (new_id, addr),
        )
    store.connection.commit()

    return Contact(id=new_id, display_name=chosen_name, addresses=tuple(sorted(found_addresses)))


def merge_contacts(store: Store, target_contact_id: int, source_contact_id: int) -> Contact:
    """Ręczne scalenie dwóch kontaktów (przenosi adresy i usuwa źródłowy)."""
    cur = store.connection.cursor()
    cur.execute(
        "UPDATE OR IGNORE contact_addresses SET contact_id = ? WHERE contact_id = ?",
        (target_contact_id, source_contact_id),
    )
    cur.execute("DELETE FROM contact_addresses WHERE contact_id = ?", (source_contact_id,))
    cur.execute("DELETE FROM contacts WHERE id = ?", (source_contact_id,))
    cur.execute("DELETE FROM contact_card_cache WHERE contact_id = ?", (source_contact_id,))
    store.connection.commit()

    cur.execute("SELECT display_name FROM contacts WHERE id = ?", (target_contact_id,))
    row = cur.fetchone()
    name = row[0] if row else "Kontakt"

    cur.execute(
        "SELECT address FROM contact_addresses WHERE contact_id = ? ORDER BY address",
        (target_contact_id,),
    )
    addrs = tuple(r[0] for r in cur.fetchall())
    return Contact(id=target_contact_id, display_name=name, addresses=addrs)


def split_contact(
    store: Store, contact_id: int, address_to_split: str, new_display_name: str
) -> Contact:
    """Ręczne rozdzielenie adresu do nowego, osobnego kontaktu."""
    cur = store.connection.cursor()
    cur.execute(
        "DELETE FROM contact_addresses WHERE contact_id = ? AND address = ?",
        (contact_id, address_to_split),
    )
    cur.execute("INSERT INTO contacts (display_name) VALUES (?)", (new_display_name,))
    new_id = cur.lastrowid
    cur.execute(
        "INSERT INTO contact_addresses (contact_id, address) VALUES (?, ?)",
        (new_id, address_to_split),
    )
    store.connection.commit()
    return Contact(id=new_id, display_name=new_display_name, addresses=(address_to_split,))


def build_contact_card(
    store: Store,
    llm: OllamaClient,
    contact: Contact,
    days: int = 30,
    config: AppConfig | None = None,
) -> ContactCard:
    """Buduje pełną kartę kontekstu kontaktu na podstawie indeksu mail_index i tematów."""
    contact_addrs = set(contact.addresses)
    all_records = store.get_all_indexed_records()

    # Wybierz wiadomości powiązane z tym kontaktem
    contact_records: list[MailIndexRecord] = []
    for r in all_records:
        sender_clean = _clean_email(r.sender)
        recipients_clean = [_clean_email(x) for x in r.recipients.split(",") if x.strip()]
        if sender_clean in contact_addrs or any(rec in contact_addrs for rec in recipients_clean):
            contact_records.append(r)

    contact_records.sort(key=lambda r: r.date or "")

    if not contact_records:
        return ContactCard(
            name=contact.display_name,
            addresses=contact.addresses,
            first_seen=None,
            last_contact=None,
            mail_count=0,
            topics=[],
            open_items=[],
            last_exchange=[],
            relationship_hint=f"Kontakt: {contact.display_name}",
            why_it_matters="Brak historii korespondencji w wybranym okresie.",
        )

    first_seen = _parse_iso_date(contact_records[0].date)
    last_contact = _parse_iso_date(contact_records[-1].date)
    mail_count = len(contact_records)

    # Ostatnie 4 wymiany z oznaczeniem kierunku („Ty → Anna”, „Anna → Ty”)
    last_exchange: list[tuple[str, str, str]] = []
    for r in contact_records[-4:]:
        dt_str = r.date[:10] if r.date else ""
        direction = getattr(r, "direction", "in")
        if direction == "out":
            kierunek = f"Ty → {contact.display_name}"
        else:
            kierunek = f"{contact.display_name} → Ty"
        summary = r.summary or r.why or clean_subject(r.subject)
        last_exchange.append((dt_str, kierunek, summary))

    # Tematy powiązane z kontaktem i otwarte sprawy (wg ostatniej wiadomości w wątku)
    thread_keys = list(dict.fromkeys(r.thread_key for r in contact_records))
    topics: list[Topic] = []
    open_items: list[str] = []

    for t_key in thread_keys:
        thread_recs = store.get_records_for_thread(t_key)
        cached_t = store.get_topic_digest_cache(t_key)

        title_val = cached_t.title if cached_t else ""
        if not title_val and thread_recs:
            title_val = clean_subject(thread_recs[-1].subject) or "Wątek"

        last_rec = thread_recs[-1] if thread_recs else None
        last_dir = getattr(last_rec, "direction", "in") if last_rec else "in"
        raw_status = cached_t.status if cached_t else ""

        if raw_status in ("zamknięte", "informacyjne"):
            status_val = raw_status
        elif last_dir == "out":
            status_val = "oczekuje_na_innych"
        else:
            status_val = "oczekuje_na_mnie"

        if status_val == "oczekuje_na_mnie":
            open_items.append(f"Czeka na Ciebie: {title_val}")
        elif status_val == "oczekuje_na_innych":
            open_items.append(f"Czeka na kontakt ({contact.display_name}): {title_val}")

        if cached_t:
            topics.append(
                Topic(
                    title=title_val,
                    participants=[],
                    who_to_whom=cached_t.who_to_whom,
                    why=cached_t.why,
                    status=cached_t.status,  # type: ignore[arg-type]
                    last_activity=_parse_iso_date(cached_t.last_mail_date),
                    importance=5,
                    mail_count=cached_t.mail_count,
                )
            )

    # Sprawdzenie pamięci podręcznej karty kontaktu w SQLite
    cur = store.connection.cursor()
    last_mail_date = contact_records[-1].date
    cached_row = None
    if contact.id is not None:
        cur.execute(
            """
            SELECT relationship_hint, why_it_matters, last_mail_date, mail_count
            FROM contact_card_cache
            WHERE contact_id = ?
            """,
            (contact.id,),
        )
        cached_row = cur.fetchone()

    if cached_row and cached_row[2] == last_mail_date and cached_row[3] == mail_count:
        rel_hint = cached_row[0]
        why_matters = cached_row[1]
    else:
        # Wywołanie LLM w celu wygenerowania zwięzłej wskazówki relacji
        cfg = config or AppConfig()
        model = pick_model("pl", cfg.ollama)

        history_lines: list[str] = []
        for r in contact_records[-6:]:
            dt = r.date[:10] if r.date else ""
            r_dir = getattr(r, "direction", "in")
            k_lbl = (
                f"Ty → {contact.display_name}"
                if r_dir == "out"
                else f"{contact.display_name} → Ty"
            )
            text_desc = r.summary or r.why or ""
            history_lines.append(f"- [{dt}] {k_lbl}: {r.subject} ({text_desc})")
        user_content = (
            f"Osoba: {contact.display_name}\n"
            f"Adresy: {', '.join(contact.addresses)}\n"
            f"Ostatnia korespondencja:\n" + "\n".join(history_lines)
        )

        system_prompt = (
            "Jesteś asystentem poczty. Na podstawie historii korespondencji z podaną osobą "
            "przygotuj zwięzłe podsumowanie relacji w formacie JSON.\n"
            "Wymagania pól JSON:\n"
            "- relationship_hint: 1 krótkie zdanie po ludzku (kim jest i w jakich sprawach pisze)\n"
            "- why_it_matters: 1 krótkie zdanie dlaczego ten kontakt jest ważny / aktualny stan\n"
            "Maksymalnie 2 krótkie zdania łącznie."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        rel_hint = (
            f"{contact.display_name} — kontakt z korespondencji e-mail ({mail_count} wiadomości)."
        )
        why_matters = open_items[0] if open_items else "Brak otwartych spraw."

        try:
            res = llm.chat_json(messages, model, CONTACT_HINT_SCHEMA)
            if isinstance(res, dict):
                rel_hint = str(res.get("relationship_hint") or rel_hint).strip()
                why_matters = str(res.get("why_it_matters") or why_matters).strip()

                if contact.id is not None:
                    c_at = datetime.now(timezone.utc).isoformat()
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO contact_card_cache
                        (contact_id, last_mail_date, mail_count, relationship_hint,
                         why_it_matters, cached_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (contact.id, last_mail_date, mail_count, rel_hint, why_matters, c_at),
                    )
                    store.connection.commit()
        except (AnalyzerError, Exception):
            pass

    return ContactCard(
        name=contact.display_name,
        addresses=contact.addresses,
        first_seen=first_seen,
        last_contact=last_contact,
        mail_count=mail_count,
        topics=topics,
        open_items=open_items,
        last_exchange=last_exchange,
        relationship_hint=rel_hint,
        why_it_matters=why_matters,
    )
