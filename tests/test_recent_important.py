"""Testy odtwarzania ważnych wiadomości z bazy po starcie (service.recent_important).

Regresja: zakładka „Wiadomości" była pusta aż do następnego cyklu, mimo że podsumowanie
(czytające z tej samej bazy) pokazywało treści, a telefon miał już wiadomości.
"""

import httpx
import pytest

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.secrets import EncryptedFileStore
from mailvoice.core.service import MailService
from mailvoice.core.store import MailIndexRecord, Store


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def secret_store(tmp_path):
    return EncryptedFileStore(tmp_path / "secrets.json", "SuperHaslo")


def _rec(uid, sender, subject, importance, date, direction="in", risk="low", risk_reasons=""):
    return MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=uid,
        message_id=f"<m{uid}@local>",
        thread_key=f"t{uid}",
        date=date,
        sender=sender,
        recipients="ja@local",
        subject=subject,
        importance=importance,
        why="Powód ważności",
        summary="Streszczenie treści",
        direction=direction,
        risk=risk,
        risk_reasons=risk_reasons,
    )


def _service(store, secret_store):
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
    )
    ollama = OllamaClient(
        config.ollama, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    return MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=ollama,
    )


def test_recent_important_returns_stored_important_in(store, secret_store):
    store.save_mail_index(_rec(3, "szef@firma.pl", "Pilne", 8, "2026-10-03T10:00:00+00:00"))
    store.save_mail_index(_rec(2, "kolega@firma.pl", "Spam", 3, "2026-10-02T10:00:00+00:00"))
    store.save_mail_index(
        _rec(4, "ja@local", "Wysłane", 9, "2026-10-03T11:00:00+00:00", direction="out")
    )

    service = _service(store, secret_store)
    items = service.recent_important()

    # Tylko przychodzący mail powyżej progu — nie spam (3<6) i nie wysłane (direction='out')
    assert len(items) == 1
    item = items[0]
    assert item.mail.sender == "szef@firma.pl"
    assert item.mail.subject == "Pilne"
    assert item.final_importance == 8
    assert item.analysis_reason == "Powód ważności"
    assert item.summary == "Streszczenie treści"
    assert item.suspicious is False


def test_recent_important_sorted_newest_first(store, secret_store):
    store.save_mail_index(_rec(1, "a@x.pl", "Starszy", 7, "2026-10-01T10:00:00+00:00"))
    store.save_mail_index(_rec(2, "b@x.pl", "Nowszy", 7, "2026-10-03T10:00:00+00:00"))

    service = _service(store, secret_store)
    items = service.recent_important()

    assert [i.mail.subject for i in items] == ["Nowszy", "Starszy"]


def test_recent_important_marks_suspicious_and_splits_reasons(store, secret_store):
    store.save_mail_index(
        _rec(
            5,
            "phish@zło.pl",
            "Dopłata",
            7,
            "2026-10-03T10:00:00+00:00",
            risk="high",
            risk_reasons="podejrzany link; nietypowy nadawca",
        )
    )

    service = _service(store, secret_store)
    items = service.recent_important()

    assert len(items) == 1
    assert items[0].suspicious is True
    assert items[0].risk_reasons == ("podejrzany link", "nietypowy nadawca")


def test_recent_important_skips_mail_ignored_by_user_rules(store, secret_store):
    """Regresja: zignorowane maile wracały na listę po restarcie programu."""
    from mailvoice.core.ignore import MailRule

    store.save_mail_index(_rec(1, "reklama@sklep.pl", "Promocja", 8, "2026-10-03T10:00:00+00:00"))
    store.save_mail_index(_rec(2, "szef@firma.pl", "Pilne", 8, "2026-10-03T11:00:00+00:00"))
    service = _service(store, secret_store)
    service.config.ignore_rules = [MailRule(sender="reklama@sklep.pl")]

    assert [i.mail.sender for i in service.recent_important()] == ["szef@firma.pl"]
