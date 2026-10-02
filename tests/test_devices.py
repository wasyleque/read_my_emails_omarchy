"""Testy modułu zarządzania urządzeniami i parowania (DeviceManager, PairingSession)."""

import sqlite3
import time
from pathlib import Path

import pytest

from mailvoice.core.devices import (
    DeviceLimitError,
    DeviceManager,
    PairingError,
    PairingLockedError,
    PairingSession,
)


def test_pairing_session_success_and_single_use():
    """Weryfikuje poprawną weryfikację kodu oraz to, że kod jest jednorazowy."""
    session = PairingSession(code="ABC234", timeout_s=120)
    assert session.is_valid() is True
    assert session.remaining_seconds > 0

    # Poprawne sprawdzenie kodu (z ignorowaniem myślników i spacji)
    assert session.verify_and_consume("abc-234") is True
    assert session.is_used is True
    assert session.is_valid() is False

    # Ponowne użycie kodu musi zostać odrzucone
    assert session.verify_and_consume("ABC234") is False


def test_pairing_session_lockout_after_5_attempts():
    """Weryfikuje blokadę sesji po 5 błędnych próbach."""
    session = PairingSession(code="XYZ789", timeout_s=120, max_attempts=5)

    for i in range(4):
        assert session.verify_and_consume("BLEDNY") is False
        assert session.is_locked is False
        assert session.attempts == i + 1

    # 5. błędna próba powoduje blokadę
    assert session.verify_and_consume("BLEDNY") is False
    assert session.is_locked is True
    assert session.is_valid() is False

    # Nawet podanie poprawnego kodu po blokadzie zostaje odrzucone
    assert session.verify_and_consume("XYZ789") is False


def test_pairing_session_expiration():
    """Weryfikuje odrzucenie wygasłego kodu."""
    past_time = time.time() - 200
    session = PairingSession(code="PAST01", timeout_s=120, created_at=past_time)

    assert session.is_valid() is False
    assert session.remaining_seconds == 0
    assert session.verify_and_consume("PAST01") is False


def test_device_manager_pair_and_verify_token():
    """Weryfikuje pełną ścieżkę parowania urządzenia i weryfikacji tokenu."""
    mgr = DeviceManager(":memory:")
    session = mgr.start_pairing_session()

    dev_id, token = mgr.pair_device(session.code, "Poco F4")
    assert dev_id.startswith("dev_")
    assert len(token) == 64  # 32 bajty hex

    # Sesja parowania powinna zostać automatycznie zamknięta
    assert mgr.get_active_session() is None

    # Weryfikacja tokenu
    device = mgr.verify_token(token)
    assert device is not None
    assert device.id == dev_id
    assert device.name == "Poco F4"
    assert device.revoked is False

    # Błędny token
    assert mgr.verify_token("niepoprawny_token_1234567890") is None

    mgr.close()


def test_device_manager_no_plaintext_token_in_database(tmp_path: Path):
    """Gwarantuje, że jawny token NIGDY nie jest zapisywany w bazie danych."""
    db_file = tmp_path / "devices.db"
    mgr = DeviceManager(db_file)
    session = mgr.start_pairing_session()

    _, token = mgr.pair_device(session.code, "Telefon Testowy")

    # Bezpośredni odczyt z pliku SQLite
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, token_hash FROM paired_devices")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    stored_hash = rows[0][2]

    # Jawny token nie może być równy zapisanemu hashowi ani znajdować się w bazie
    assert token != stored_hash
    db_bytes = db_file.read_bytes()
    assert token.encode("utf-8") not in db_bytes

    mgr.close()


def test_device_manager_device_limit():
    """Weryfikuje egzekwowanie limitu liczby sparowanych urządzeń."""
    mgr = DeviceManager(":memory:")

    # Parujemy 2 urządzenia z limitem max_devices=2
    s1 = mgr.start_pairing_session()
    mgr.pair_device(s1.code, "Urządzenie 1", max_devices=2)

    s2 = mgr.start_pairing_session()
    mgr.pair_device(s2.code, "Urządzenie 2", max_devices=2)

    # Próba sparowania 3. urządzenia musi rzucić DeviceLimitError
    s3 = mgr.start_pairing_session()
    with pytest.raises(DeviceLimitError):
        mgr.pair_device(s3.code, "Urządzenie 3", max_devices=2)

    mgr.close()


def test_device_manager_revocation():
    """Weryfikuje odwołanie dostępu dla urządzenia."""
    mgr = DeviceManager(":memory:")
    session = mgr.start_pairing_session()
    dev_id, token = mgr.pair_device(session.code, "Telefon")

    assert mgr.verify_token(token) is not None

    # Odwołanie urządzenia
    ok = mgr.revoke_device(dev_id)
    assert ok is True

    # Po odwołaniu token jest odrzucany
    assert mgr.verify_token(token) is None

    # Urządzenie widoczne na liście z flagą revoked=True
    devices = mgr.list_devices(include_revoked=True)
    assert len(devices) == 1
    assert devices[0].revoked is True

    # Nie widać go na liście aktywnych urządzeń
    assert len(mgr.list_devices(include_revoked=False)) == 0

    mgr.close()


def test_device_manager_migration_existing_db(tmp_path: Path):
    """Weryfikuje automatyczne utworzenie tabeli w istniejącej bazie danych."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE legacy_data (id INT)")
    conn.commit()
    conn.close()

    mgr = DeviceManager(db_file)
    devices = mgr.list_devices()
    assert devices == []

    session = mgr.start_pairing_session()
    dev_id, token = mgr.pair_device(session.code, "Nowy telefon")
    assert mgr.verify_token(token) is not None

    mgr.close()


def test_device_manager_pairing_errors():
    """Weryfikuje błędy przy braku aktywnej sesji lub błędnym kodzie."""
    mgr = DeviceManager(":memory:")

    # Brak sesji
    with pytest.raises(PairingError, match="Brak aktywnej sesji"):
        mgr.pair_device("123456", "Telefon")

    # Błędny kod
    s = mgr.start_pairing_session()
    with pytest.raises(PairingError, match="Niepoprawny kod"):
        mgr.pair_device("ZLYKOD", "Telefon")

    # Zablokowana sesja
    for _ in range(4):
        s.verify_and_consume("BLEDNY")
    assert s.is_locked is True

    with pytest.raises(PairingLockedError):
        mgr.pair_device(s.code, "Telefon")

    mgr.close()
