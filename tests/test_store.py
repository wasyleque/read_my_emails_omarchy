import pytest

from mailvoice.core.store import Store


def test_last_uid_upsert_and_default():
    store = Store()
    assert store.get_last_uid("a", "INBOX", 1) == 0
    store.set_last_uid("a", "INBOX", 1, 10)
    store.set_last_uid("a", "INBOX", 1, 20)
    assert store.get_last_uid("a", "INBOX", 1) == 20


def test_uidvalidity_change_resets_last_uid():
    store = Store()
    store.set_last_uid("a", "INBOX", 1, 20)
    assert store.get_last_uid("a", "INBOX", 2) == 0


def test_dedup_by_key():
    store = Store()
    assert not store.is_seen("a", "INBOX", 1, 5, None)
    store.mark_seen("a", "INBOX", 1, 5, None)
    assert store.is_seen("a", "INBOX", 1, 5, None)
    assert not store.is_seen("a", "INBOX", 1, 6, None)


def test_dedup_by_message_id_same_account_only():
    store = Store()
    store.mark_seen("a", "INBOX", 1, 5, "<m@x>")
    assert store.is_seen("a", "INBOX", 2, 99, "<m@x>")
    assert store.is_seen("a", "Archive", 1, 7, "<m@x>")
    assert not store.is_seen("b", "INBOX", 1, 5, "<m@x>")


def test_invalid_status_raises():
    store = Store()
    with pytest.raises(ValueError):
        store.mark_seen("a", "INBOX", 1, 5, "<m@x>", status="bogus")


def test_backlog_declined_status_is_seen():
    store = Store()
    store.mark_seen("a", "INBOX", 1, 5, "<m@x>", status="backlog_declined")
    assert store.is_seen("a", "INBOX", 1, 5, "<m@x>")


def test_persistence_on_file(tmp_path):
    db = tmp_path / "mail.db"
    store = Store(db)
    store.mark_seen("a", "INBOX", 1, 5, "<m@x>", importance=7)
    store.set_last_uid("a", "INBOX", 1, 5)
    store.close()
    again = Store(db)
    assert again.is_seen("a", "INBOX", 1, 5, "<m@x>")
    assert again.get_last_uid("a", "INBOX", 1) == 5


def test_has_last_uid_distinguishes_zero_baseline_from_missing():
    store = Store()
    assert not store.has_last_uid("a", "INBOX", 1)
    store.set_last_uid("a", "INBOX", 1, 0)
    assert store.has_last_uid("a", "INBOX", 1)
    assert not store.has_last_uid("a", "INBOX", 2)


def test_store_usable_from_another_thread_file_db(tmp_path):
    """Regresja: „SQLite objects created in a thread can only be used in that same thread”."""
    import threading

    store = Store(tmp_path / "t.db")  # utworzony w wątku głównym
    errors: list[Exception] = []

    def worker():  # jak CycleWorker (QThread)
        try:
            store.mark_seen("a", "INBOX", 1, 5, "<m@x>")
            store.set_last_uid("a", "INBOX", 1, 5)
            assert store.is_seen("a", "INBOX", 1, 5, "<m@x>")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert errors == []
    assert store.is_seen("a", "INBOX", 1, 5, "<m@x>")  # widoczne w wątku głównym
    assert store.get_last_uid("a", "INBOX", 1) == 5
    store.close()


def test_store_memory_usable_from_another_thread():
    import threading

    store = Store()
    errors: list[Exception] = []

    def worker():
        try:
            store.mark_seen("a", "INBOX", 1, 1, None)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert errors == [] and store.is_seen("a", "INBOX", 1, 1, None)
