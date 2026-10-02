"""Testy modułu kart kontaktów (core/contacts.py)."""

import json
from datetime import datetime, timezone

import httpx

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import OllamaConfig
from mailvoice.core.contacts import (
    Contact,
    ContactCard,
    build_contact_card,
    merge_contacts,
    resolve_contact,
    split_contact,
)
from mailvoice.core.store import MailIndexRecord, Store


def _make_record(
    sender: str,
    recipients: str,
    subject: str = "Spotkanie",
    thread_key: str = "t1",
    uid: int = 1,
    summary: str = "Omówienie planów.",
    date: str | None = None,
) -> MailIndexRecord:
    dt = date or datetime.now(timezone.utc).isoformat()
    return MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=uid,
        message_id=f"<m{uid}@test.pl>",
        thread_key=thread_key,
        date=dt,
        sender=sender,
        recipients=recipients,
        subject=subject,
        importance=7,
        why="Sprawa bieżąca",
        summary=summary,
    )


def test_resolve_contact_unknown():
    store = Store(":memory:")
    # Brak w bazie i brak w mail_index -> None
    assert resolve_contact(store, "nieznajomy@obcy.pl") is None
    assert resolve_contact(store, "") is None


def test_resolve_contact_from_mail_index():
    store = Store(":memory:")
    store.save_mail_index(
        _make_record(
            sender="Piotr Kowalski <piotr@firma.pl>",
            recipients="me@corp.com",
            subject="Raport finansowy",
        )
    )

    # Rozpoznanie po adresie e-mail
    c1 = resolve_contact(store, "piotr@firma.pl")
    assert isinstance(c1, Contact)
    assert c1.display_name == "Piotr Kowalski"
    assert "piotr@firma.pl" in c1.addresses

    # Rozpoznanie po nazwisku
    c2 = resolve_contact(store, "Piotr Kowalski")
    assert c2 is not None
    assert c2.id == c1.id


def test_resolve_contact_conservative_merge():
    store = Store(":memory:")
    # Ten sam Piotr Kowalski z dwoma adresami w tej samej domenie
    store.save_mail_index(
        _make_record(
            sender="Piotr Kowalski <piotr@firma.pl>",
            recipients="me@corp.com",
            uid=1,
        )
    )
    store.save_mail_index(
        _make_record(
            sender="Piotr Kowalski <p.kowalski@firma.pl>",
            recipients="me@corp.com",
            uid=2,
        )
    )

    c = resolve_contact(store, "piotr@firma.pl")
    assert c is not None
    assert "piotr@firma.pl" in c.addresses

    c_merged = resolve_contact(store, "p.kowalski@firma.pl")
    assert c_merged is not None
    assert c_merged.id == c.id
    assert "p.kowalski@firma.pl" in c_merged.addresses
    assert len(c_merged.addresses) == 2


def test_merge_and_split_contacts():
    store = Store(":memory:")
    store.save_mail_index(
        _make_record(
            sender="Anna Nowak <anna1@corp.pl>",
            recipients="me@corp.com",
            uid=1,
        )
    )
    store.save_mail_index(
        _make_record(
            sender="Anna Nowak Prywatny <anna.private@home.pl>",
            recipients="me@corp.com",
            uid=2,
        )
    )

    c1 = resolve_contact(store, "anna1@corp.pl")
    c2 = resolve_contact(store, "anna.private@home.pl")
    assert c1 is not None and c2 is not None
    assert c1.id != c2.id

    # Ręczne scalenie c2 do c1
    merged = merge_contacts(store, target_contact_id=c1.id, source_contact_id=c2.id)
    assert merged.id == c1.id
    assert "anna1@corp.pl" in merged.addresses
    assert "anna.private@home.pl" in merged.addresses

    # Ręczne rozdzielenie adresu prywatnego
    split_c = split_contact(
        store,
        contact_id=c1.id,
        address_to_split="anna.private@home.pl",
        new_display_name="Anna Nowak (Dom)",
    )
    assert split_c.id != c1.id
    assert split_c.display_name == "Anna Nowak (Dom)"
    assert split_c.addresses == ("anna.private@home.pl",)


def test_build_contact_card_llm_and_caching():
    store = Store(":memory:")
    store.save_mail_index(
        _make_record(
            sender="Piotr Kowalski <piotr@firma.pl>",
            recipients="me@corp.com",
            subject="Faktura za remont",
            summary="Przesłano fakturę VAT za remont biura.",
            thread_key="thread-faktura",
            uid=10,
        )
    )
    # Zapiszmy status wątku w pamięci podręcznej digest
    store.save_topic_digest_cache(
        thread_key="thread-faktura",
        last_mail_date=datetime.now(timezone.utc).isoformat(),
        mail_count=1,
        title="Faktura za remont",
        why="Oczekuje na akceptację płatności.",
        status="oczekuje_na_mnie",
        who_to_whom=["Piotr -> Użytkownik: faktura"],
    )

    contact = resolve_contact(store, "piotr@firma.pl")
    assert contact is not None

    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        resp = {
            "relationship_hint": "Piotr Kowalski — księgowy firmy remontowej.",
            "why_it_matters": "Czeka na opłacenie faktury za remont.",
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = OllamaClient(OllamaConfig(), transport=httpx.MockTransport(handler))

    # Pierwsze wywołanie -> pyta LLM
    card1 = build_contact_card(store, client, contact)
    assert isinstance(card1, ContactCard)
    assert card1.name == "Piotr Kowalski"
    assert card1.relationship_hint == "Piotr Kowalski — księgowy firmy remontowej."
    assert card1.why_it_matters == "Czeka na opłacenie faktury za remont."
    assert len(card1.open_items) == 1
    assert "Faktura za remont" in card1.open_items[0]
    assert len(card1.last_exchange) == 1
    assert call_count == 1

    # Drugie wywołanie -> korzysta z cache w SQLite, LLM nie jest pytany ponownie
    card2 = build_contact_card(store, client, contact)
    assert card2.relationship_hint == card1.relationship_hint
    assert call_count == 1


def test_build_contact_card_llm_error_fallback():
    store = Store(":memory:")
    store.save_mail_index(
        _make_record(
            sender="Karol <karol@partner.com>",
            recipients="me@corp.com",
            subject="Zaproszenie na webinar",
            uid=20,
        )
    )

    contact = resolve_contact(store, "karol@partner.com")
    assert contact is not None

    def handler(request):
        return httpx.Response(500, text="Ollama offline")

    client = OllamaClient(OllamaConfig(), transport=httpx.MockTransport(handler))

    # Błąd LLM nie rzuca wyjątku, karta zwraca bezpieczny fallback
    card = build_contact_card(store, client, contact)
    assert card.name == "Karol"
    assert "Karol" in card.relationship_hint
    assert card.mail_count == 1
