"""Testy indeksu wiadomości (mail_index) w Store oraz retencji danych."""

from datetime import datetime, timedelta, timezone

from mailvoice.core.store import MailIndexRecord, Store


def test_mail_index_crud_and_thread_query(tmp_path):
    db_file = tmp_path / "test.db"
    store = Store(str(db_file))

    record1 = MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=10,
        uid=101,
        message_id="<msg1@test>",
        thread_key="thread_alpha",
        date="2026-10-01T10:00:00+00:00",
        sender="anna@firma.pl",
        recipients="jan@firma.pl, piotr@firma.pl",
        subject="Projekt Alpha",
        importance=8,
        why="Pilne ustalenia projektowe",
        summary="Krótkie streszczenie wątku...",
    )
    store.save_mail_index(record1)

    fetched = store.get_mail_index("acc1", "INBOX", 10, 101)
    assert fetched is not None
    assert fetched.message_id == "<msg1@test>"
    assert fetched.thread_key == "thread_alpha"
    assert fetched.importance == 8
    assert fetched.why == "Pilne ustalenia projektowe"

    # Dodanie drugiej wiadomości w tym samym wątku
    record2 = MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=10,
        uid=102,
        message_id="<msg2@test>",
        thread_key="thread_alpha",
        date="2026-10-01T11:00:00+00:00",
        sender="jan@firma.pl",
        recipients="anna@firma.pl",
        subject="Re: Projekt Alpha",
        importance=7,
        why="Odpowiedź Jana",
        summary="",
    )
    store.save_mail_index(record2)

    thread_items = store.get_records_for_thread("thread_alpha")
    assert len(thread_items) == 2
    assert thread_items[0].uid == 101
    assert thread_items[1].uid == 102


def test_mail_index_purge_older_than(tmp_path):
    store = Store(str(tmp_path / "purge_test.db"))
    now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

    # Wiadomość sprzed 100 dni
    old_date = (now - timedelta(days=100)).isoformat()
    old_record = MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=1,
        message_id="<old@test>",
        thread_key="t_old",
        date=old_date,
        sender="stary@test.pl",
        recipients="me@test.pl",
        subject="Stary temat",
        importance=1,
        why="",
        summary="",
    )
    store.save_mail_index(old_record)

    # Wiadomość sprzed 10 dni
    fresh_date = (now - timedelta(days=10)).isoformat()
    fresh_record = MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=2,
        message_id="<fresh@test>",
        thread_key="t_fresh",
        date=fresh_date,
        sender="nowy@test.pl",
        recipients="me@test.pl",
        subject="Świeży temat",
        importance=8,
        why="",
        summary="",
    )
    store.save_mail_index(fresh_record)

    # Usunięcie starszych niż 90 dni
    deleted = store.purge_older_than(90, now=now)
    assert deleted == 1

    assert store.get_mail_index("acc1", "INBOX", 1, 1) is None
    assert store.get_mail_index("acc1", "INBOX", 1, 2) is not None


def test_store_migration_without_data_loss(tmp_path):
    """Weryfikuje, że dodanie tabeli mail_index nie narusza istniejących wpisów w seen."""
    db_file = tmp_path / "legacy.db"
    store_v1 = Store(str(db_file))
    store_v1.mark_seen("acc1", "INBOX", 1, 55, "<m55@test>", status="analyzed", importance=9)
    store_v1.close()

    # Ponowne otwarcie bazy - migracja
    store_v2 = Store(str(db_file))
    assert store_v2.is_seen("acc1", "INBOX", 1, 55, "<m55@test>") is True
    # Nowa tabela działa
    all_indexed = store_v2.get_all_indexed_records()
    assert len(all_indexed) == 0
