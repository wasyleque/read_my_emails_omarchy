"""Testy warstwy usługowej MailService (service.py)."""

import json
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.scheduler import NotificationAction
from mailvoice.core.secrets import EncryptedFileStore
from mailvoice.core.service import (
    AskReminder,
    BacklogQuestion,
    BeepReminder,
    ContactCardReady,
    MailService,
    NewImportant,
    SearchResults,
    ServiceError,
    SuspiciousMail,
)
from mailvoice.core.store import MailIndexRecord, Store
from tests.test_imap_fetch import FakeMailboxClient
from tests.test_scheduler import FakeClock


def _make_email(sender: str, subject: str, body: str, message_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg["Date"] = "Wed, 01 Oct 2026 12:00:00 +0000"
    msg.set_content(body)
    return msg.as_bytes()


@pytest.fixture
def secret_store(tmp_path: Path):
    path = tmp_path / "secrets.json"
    return EncryptedFileStore(path, "SuperHaslo")


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_service_important_mail_triggers_event(store, secret_store):
    clock = FakeClock()
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
        notify_mode="beep",
        beep_repeat_minutes=5,
    )
    secret_store.set("acc1", "Haslo123")

    client = FakeMailboxClient(uidvalidity=1)
    client.folders["INBOX"][1] = _make_email(
        sender="szef@firma.pl", subject="Pilne", body="Ważna sprawa", message_id="<m1@local>"
    )
    # Ustawienie last_uid żeby to był nowy mail
    store.set_last_uid("acc1", "INBOX", 1, 0)

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        resp = {"importance": 8, "reason": "Ważne", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    ollama = OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama))

    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=ollama,
        client_factory=lambda acc: client,
        clock=clock,
    )

    # Uruchomienie kroku tick -> uruchamia cykl
    service.tick()

    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], NewImportant)
    assert events[0].action == NotificationAction.BEEP
    assert len(events[0].items) == 1
    assert events[0].items[0].uid == 1


def test_service_beep_mode_repeats_and_confirm(store, secret_store):
    clock = FakeClock()
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
        notify_mode="beep",
        beep_repeat_minutes=5,
    )
    secret_store.set("acc1", "Haslo123")

    client = FakeMailboxClient(uidvalidity=1)
    client.folders["INBOX"][1] = _make_email("a@a.pl", "S", "B", "<m@local>")
    store.set_last_uid("acc1", "INBOX", 1, 0)

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        resp = {"importance": 9, "reason": "r", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama)),
        client_factory=lambda acc: client,
        clock=clock,
    )

    service.tick()
    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], NewImportant)

    # Po 5 minutach kolejny tick generuje BeepReminder
    clock.advance(5)
    service.tick()
    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], BeepReminder)

    # Potwierdzenie przez użytkownika ucisza powiadomienia
    service.user_confirm()
    clock.advance(5)
    service.tick()
    assert len(service.poll_events()) == 0


def test_service_ask_mode_decline_and_retry(store, secret_store):
    clock = FakeClock()
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
        notify_mode="ask",
        ask_retry_minutes=15,
    )
    secret_store.set("acc1", "Haslo123")

    client = FakeMailboxClient(uidvalidity=1)
    client.folders["INBOX"][1] = _make_email("a@a.pl", "S", "B", "<m@local>")
    store.set_last_uid("acc1", "INBOX", 1, 0)

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        resp = {"importance": 9, "reason": "r", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama)),
        client_factory=lambda acc: client,
        clock=clock,
    )

    service.tick()
    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], NewImportant)
    assert events[0].action == NotificationAction.ASK

    # Użytkownik mówi "nie"
    service.user_decline()

    # Po 10 minutach - cisza
    clock.advance(10)
    service.tick()
    assert len(service.poll_events()) == 0

    # Po kolejnych 5 minutach (łącznie 15) - ponowne pytanie głosowe
    clock.advance(5)
    service.tick()
    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], AskReminder)


def test_service_backlog_question_and_resolve(store, secret_store):
    clock = FakeClock()
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
    )
    secret_store.set("acc1", "Haslo123")

    client = FakeMailboxClient(uidvalidity=2)
    client.folders["INBOX"][1] = _make_email("b@b.pl", "Stary", "B", "<old@local>")
    client.unseen_uids["INBOX"] = {1}
    store.set_last_uid("acc1", "INBOX", 2, 1)

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        resp = {"importance": 9, "reason": "r", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama)),
        client_factory=lambda acc: client,
        clock=clock,
    )

    # Wymuszenie sprawdzenia zaległości
    service.trigger_cycle(check_backlog=True)

    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], BacklogQuestion)
    assert events[0].count == 1

    # Rozstrzygnięcie zaległości
    service.resolve_backlog(accepted=True)
    assert store.get_seen_status("acc1", "INBOX", 2, 1) == "analyzed"


def test_service_missing_password_emits_error_does_not_crash(store, secret_store):
    clock = FakeClock()
    config = AppConfig(
        accounts=[AccountConfig(name="acc_without_pwd", host="imap.local", folders=["INBOX"])],
    )
    # Brak hasła w secret_store!

    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=OllamaClient(config.ollama),
        clock=clock,
    )

    # tick nie powinien rzucić wyjątkiem
    service.tick()

    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], ServiceError)
    assert "Brak hasła" in events[0].message


def test_service_restores_pending_backlog_on_startup(store, secret_store):
    # W bazie istnieje nieobsłużona zaległość
    store.mark_seen("acc1", "INBOX", 1, 10, "<p@local>", status="backlog_pending", importance=8)

    config = AppConfig()
    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=OllamaClient(config.ollama),
    )

    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], BacklogQuestion)
    assert events[0].count == 1
    assert events[0].items[0].uid == 10


def test_service_contact_context_emits_event(store, secret_store):
    config = AppConfig()

    def handler(request):
        resp = {
            "relationship_hint": "Główny księgowy",
            "why_it_matters": "Rozliczenia kwartalne i podatki",
            "open_items": ["Zatwierdzenie faktury 45/2026"],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = OllamaClient(config.ollama, transport=httpx.MockTransport(handler))
    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=client,
    )

    # 1. Nieznany kontakt
    card_none = service.contact_context("nieznany@test.pl")
    assert card_none is None
    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], ContactCardReady)
    assert events[0].card is None
    assert events[0].address_or_name == "nieznany@test.pl"

    # 2. Znany kontakt w indeksie
    record = MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=1,
        message_id="<m1@local>",
        thread_key="t1",
        date="2026-10-01T12:00:00+00:00",
        sender="Jan Kowalski <jan@firma.pl>",
        recipients="me@corp.com",
        subject="Faktura 45/2026",
        importance=8,
        why="Płatność",
        summary="Przesyłam fakturę.",
    )
    store.save_mail_index(record)

    card = service.contact_context("jan@firma.pl")
    assert card is not None
    assert card.name == "Jan Kowalski"
    assert "księgowy" in card.relationship_hint

    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], ContactCardReady)
    assert events[0].card == card


def test_service_ai_search_emits_search_results(store, secret_store):
    config = AppConfig()

    record = MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=10,
        message_id="<m10@local>",
        thread_key="t10",
        date="2026-10-01T12:00:00+00:00",
        sender="Piotr Nowak <nowak@firma.pl>",
        recipients="me@corp.com",
        subject="Faktura za serwery",
        importance=8,
        why="Opłata",
        summary="Faktura miesięczna za hosting.",
    )
    store.save_mail_index(record)

    def handler(request):
        resp = {
            "ranked_uids": [
                {
                    "uid": 10,
                    "score": 0.9,
                    "confidence": "wysoka",
                    "why_probable": "Faktura za serwery zgadza się z tematem.",
                }
            ]
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = OllamaClient(config.ollama, transport=httpx.MockTransport(handler))
    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=client,
    )

    hits = service.ai_search("faktura za serwer")
    assert len(hits) == 1
    assert hits[0].mail_ref.uid == 10
    assert hits[0].confidence == "wysoka"

    events = service.poll_events()
    assert len(events) == 1
    assert isinstance(events[0], SearchResults)
    assert events[0].query == "faktura za serwer"
    assert len(events[0].hits) == 1


def test_service_suspicious_mail_triggers_event(store, secret_store):
    clock = FakeClock()
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
        notify_mode="beep",
    )
    secret_store.set("acc1", "Haslo123")

    client = FakeMailboxClient(uidvalidity=1)
    store.set_last_uid("acc1", "INBOX", 1, 0)

    phish_bytes = (
        b'From: "Bank PKO BP" <security@fakepko.xyz>\r\n'
        b"To: me@example.com\r\n"
        b"Subject: Pilne: blokada konta!\r\n"
        b"Message-ID: <phish_srv_1@fakepko.xyz>\r\n"
        b"Date: Wed, 01 Oct 2026 12:00:00 +0000\r\n"
        b"Authentication-Results: spf=fail dkim=fail\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Kliknij: http://fakepko.xyz/login"
    )
    client.folders["INBOX"][1] = phish_bytes

    ollama = OllamaClient("http://lan:11434", "http://127.0.0.1:11434")
    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=ollama,
        client_factory=lambda _: client,
        clock=clock,
    )

    res = service.trigger_cycle()
    assert len(res.suspicious) == 1
    assert len(res.important) == 0

    events = service.poll_events()
    suspicious_events = [e for e in events if isinstance(e, SuspiciousMail)]
    assert len(suspicious_events) == 1
    assert suspicious_events[0].mail.mail.message_id == "<phish_srv_1@fakepko.xyz>"
    assert len(suspicious_events[0].reasons) > 0
