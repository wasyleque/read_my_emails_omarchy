"""Testy modułu pobierania wiadomości IMAP (imap_fetch.py)."""

from datetime import date
from email.message import EmailMessage
from typing import Sequence

import pytest

from mailvoice.core.imap_fetch import (
    FetchError,
    ImapToolsClient,
    commit_progress,
    fetch_backlog,
    fetch_new,
    fetch_sent_for_index,
    fetch_sent_message_ids,
    normalize_message_id,
)
from mailvoice.core.store import Store


def _make_raw_email(
    message_id: str = "<msg1@example.com>",
    sender: str = "sender@example.com",
    subject: str = "Test Subject",
    body: str = "Treść testowa wiadomości",
    in_reply_to: str | None = None,
    references: str | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["From"] = sender
    msg["Subject"] = subject
    msg["Date"] = "Wed, 01 Oct 2026 12:00:00 +0000"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    return msg.as_bytes()


class FakeMailboxClient:
    """Fałszywy klient skrzynki pocztowej operujący w pamięci."""

    def __init__(self, uidvalidity: int = 1000):
        self.uidvalidity = uidvalidity
        # folder -> dict[uid, bytes]
        self.folders: dict[str, dict[int, bytes]] = {"INBOX": {}, "Sent": {}}
        # folder -> set[uid]
        self.unseen_uids: dict[str, set[int]] = {"INBOX": set(), "Sent": set()}
        self.sent_headers: list[str] = []
        self.closed = False

    def get_uidvalidity(self, folder: str) -> int:
        if folder not in self.folders:
            raise FetchError(f"Folder '{folder}' does not exist")
        return self.uidvalidity

    def get_uids_greater_than(self, folder: str, min_uid: int) -> list[int]:
        if folder not in self.folders:
            raise FetchError(f"Folder '{folder}' does not exist")
        folder_emails = self.folders.get(folder, {})
        return sorted([uid for uid in folder_emails if uid > min_uid])

    def get_uids_since(self, folder: str, since_date: date) -> list[int]:
        if folder not in self.folders:
            raise FetchError(f"Folder '{folder}' does not exist")
        folder_emails = self.folders.get(folder, {})
        return sorted(list(folder_emails.keys()))

    def get_unseen_uids(self, folder: str, since_date: date) -> list[int]:
        if folder not in self.folders:
            raise FetchError(f"Folder '{folder}' does not exist")
        unseen = self.unseen_uids.get(folder, set())
        return sorted(list(unseen))

    def fetch_raw_batch(self, folder: str, uids: Sequence[int]) -> list[tuple[int, bytes]]:
        if folder not in self.folders:
            raise FetchError(f"Folder '{folder}' does not exist")
        folder_emails = self.folders.get(folder, {})
        return [(uid, folder_emails[uid]) for uid in uids if uid in folder_emails]

    def get_sent_message_ids(self, folder: str, since_date: date) -> list[str]:
        if folder not in self.folders:
            raise FetchError(f"Folder '{folder}' does not exist")
        return list(self.sent_headers)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_normalize_message_id():
    assert normalize_message_id("test@domain.com") == "<test@domain.com>"
    assert normalize_message_id("<test@domain.com>") == "<test@domain.com>"
    assert normalize_message_id("") == ""
    assert normalize_message_id(None) == ""


def test_fetch_new_empty(store):
    client = FakeMailboxClient()
    items = fetch_new(client, store, "acc1", "INBOX")
    assert items == []


def test_fetch_new_and_commit_progress(store):
    client = FakeMailboxClient(uidvalidity=123)
    client.folders["INBOX"][10] = _make_raw_email(message_id="<id10@example.com>")
    client.folders["INBOX"][11] = _make_raw_email(message_id="<id11@example.com>")

    items = fetch_new(client, store, "acc1", "INBOX")
    assert len(items) == 2
    assert items[0][0] == 10
    assert items[0][1].message_id == "<id10@example.com>"
    assert items[1][0] == 11
    assert items[1][1].message_id == "<id11@example.com>"

    # fetch_new nie oznacza wiadomości jako seen automatycznie
    assert store.is_seen("acc1", "INBOX", 123, 10, "<id10@example.com>") is False
    # last_uid nie zmienia się automatycznie bez commit_progress
    assert store.get_last_uid("acc1", "INBOX", 123) == 0

    # Przesunięcie postępu
    commit_progress(store, "acc1", "INBOX", 123, 11)
    assert store.get_last_uid("acc1", "INBOX", 123) == 11

    # Kolejny fetch_new nie pobierze już wiadomości <= 11
    client.folders["INBOX"][12] = _make_raw_email(message_id="<id12@example.com>")
    new_items = fetch_new(client, store, "acc1", "INBOX")
    assert len(new_items) == 1
    assert new_items[0][0] == 12


def test_fetch_new_deduplication_by_message_id(store):
    client = FakeMailboxClient(uidvalidity=123)
    client.folders["INBOX"][10] = _make_raw_email(message_id="<duplicate@example.com>")

    # Oznaczamy ten sam message_id jako widziany w innym folderze lub wcześniejszej sesji
    store.mark_seen("acc1", "Archive", 100, 1, "<duplicate@example.com>", status="analyzed")

    items = fetch_new(client, store, "acc1", "INBOX")
    assert len(items) == 0


def test_fetch_backlog(store):
    client = FakeMailboxClient(uidvalidity=555)
    client.folders["INBOX"][1] = _make_raw_email(message_id="<old1@example.com>")
    client.folders["INBOX"][2] = _make_raw_email(message_id="<old2@example.com>")
    client.folders["INBOX"][3] = _make_raw_email(message_id="<new1@example.com>")

    # Wiadomości 1 i 2 to UNSEEN
    client.unseen_uids["INBOX"] = {1, 2}

    # last_uid to 2
    store.set_last_uid("acc1", "INBOX", 555, 2)
    # Wiadomość 1 już była w seen (np. wcześniej przeanalizowana)
    store.mark_seen("acc1", "INBOX", 555, 1, "<old1@example.com>", status="analyzed")

    backlog = fetch_backlog(client, store, "acc1", "INBOX", days=30)
    assert len(backlog) == 1
    assert backlog[0][0] == 2
    assert backlog[0][1].message_id == "<old2@example.com>"


def test_fetch_sent_message_ids(store):
    client = FakeMailboxClient()
    client.sent_headers = ["<sent1@domain.com>", "sent2@domain.com", "   "]

    sent_ids = fetch_sent_message_ids(client, "Sent", days=14)
    assert sent_ids == frozenset({"<sent1@domain.com>", "<sent2@domain.com>"})


def test_imap_tools_client_sanitizes_password():
    client = ImapToolsClient(
        host="non-existent.local",
        port=993,
        username="user@example.com",
        password="SuperSecretPassword123",
    )
    with pytest.raises(FetchError) as exc_info:
        client.get_uidvalidity("INBOX")

    error_msg = str(exc_info.value)
    assert "SuperSecretPassword123" not in error_msg


def test_fetch_sent_for_index_basic(store):
    client = FakeMailboxClient(uidvalidity=999)
    client.folders["Sent"][1] = _make_raw_email(message_id="<sent1@example.com>", subject="Sent 1")
    client.folders["Sent"][2] = _make_raw_email(message_id="<sent2@example.com>", subject="Sent 2")

    items = fetch_sent_for_index(client, store, "acc1", sent_folder="Sent", days=30)
    assert len(items) == 2
    assert items.folder == "Sent"
    assert items.uidvalidity == 999
    assert items[0][0] == 1
    assert items[0][1].message_id == "<sent1@example.com>"
    assert items[1][0] == 2
    assert items[1][1].message_id == "<sent2@example.com>"


def test_fetch_sent_for_index_skips_already_indexed(store):
    from mailvoice.core.store import MailIndexRecord

    client = FakeMailboxClient(uidvalidity=999)
    client.folders["Sent"][1] = _make_raw_email(message_id="<sent1@example.com>", subject="Sent 1")
    client.folders["Sent"][2] = _make_raw_email(message_id="<sent2@example.com>", subject="Sent 2")

    # Wiadomość 1 już w indeksie tego konta
    store.save_mail_index(
        MailIndexRecord(
            account="acc1",
            folder="Sent",
            uidvalidity=999,
            uid=1,
            message_id="<sent1@example.com>",
            thread_key="<sent1@example.com>",
            date="2026-10-01T12:00:00+00:00",
            sender="me@example.com",
            recipients="to@example.com",
            subject="Sent 1",
            importance=0,
            why="",
            summary="",
            direction="out",
        )
    )

    items = fetch_sent_for_index(client, store, "acc1", sent_folder="Sent", days=30)
    assert len(items) == 1
    assert items[0][0] == 2
    assert items[0][1].message_id == "<sent2@example.com>"


def test_fetch_sent_for_index_folder_fallback(store):
    client = FakeMailboxClient(uidvalidity=777)
    # Usuwamy domyślny 'Sent', tworzymy '[Gmail]/Sent Mail'
    del client.folders["Sent"]
    client.folders["[Gmail]/Sent Mail"] = {
        5: _make_raw_email(message_id="<gmail_sent@example.com>", subject="Gmail sent")
    }

    # Przekazujemy folder 'NonExistent', a funkcja powinna znaleźć '[Gmail]/Sent Mail'
    items = fetch_sent_for_index(client, store, "acc1", sent_folder="NonExistent", days=30)
    assert len(items) == 1
    assert items.folder == "[Gmail]/Sent Mail"
    assert items.uidvalidity == 777
    assert items[0][0] == 5
    assert items[0][1].message_id == "<gmail_sent@example.com>"


def test_fetch_sent_for_index_missing_folder_raises(store):
    client = FakeMailboxClient(uidvalidity=100)
    client.folders.clear()
    client.folders["INBOX"] = {}

    with pytest.raises(FetchError) as exc_info:
        fetch_sent_for_index(client, store, "acc1", sent_folder="MissingFolder", days=30)
    assert "Nie odnaleziono folderu wiadomości wysłanych" in str(exc_info.value)


def test_fetch_sent_for_index_limit(store):
    client = FakeMailboxClient(uidvalidity=1000)
    for i in range(1, 15):
        client.folders["Sent"][i] = _make_raw_email(
            message_id=f"<msg_{i}@example.com>", subject=f"Subject {i}"
        )

    items = fetch_sent_for_index(client, store, "acc1", sent_folder="Sent", limit=5)
    assert len(items) == 5
    # Powinny być najnowsze UID (10, 11, 12, 13, 14)
    uids = [item[0] for item in items]
    assert uids == [10, 11, 12, 13, 14]
