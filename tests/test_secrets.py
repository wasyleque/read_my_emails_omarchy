"""Testy magazynu sekretów (secrets.py)."""

import hashlib
import os
from pathlib import Path

import keyring
import keyring.backends.fail
import pytest
from keyring.backend import KeyringBackend

from mailvoice.core import secrets as secrets_mod
from mailvoice.core.imap_fetch import FetchError, ImapToolsClient
from mailvoice.core.secrets import (
    EncryptedFileStore,
    Fido2Store,
    KeyringStore,
    SecretStoreError,
    SecretStoreUnavailable,
    create_store,
)


class InMemoryKeyring(KeyringBackend):
    """Atrapa systemowego pęku kluczy w pamięci na potrzeby testów."""

    priority = 10

    def __init__(self) -> None:
        self._vault: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._vault.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._vault[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._vault.pop((service, username), None)


class FakeHmacDevice:
    """Atrapa fizycznego klucza FIDO2 hmac-secret."""

    def __init__(self, fail_derive: bool = False) -> None:
        self._keys: dict[bytes, bytes] = {}
        self.fail_derive = fail_derive

    def enroll(self) -> bytes:
        cred_id = os.urandom(16)
        secret = os.urandom(32)
        self._keys[cred_id] = secret
        return cred_id

    def derive(self, credential_id: bytes, salt: bytes) -> bytes:
        if self.fail_derive or credential_id not in self._keys:
            raise RuntimeError("Urządzenie FIDO2 nie rozpoznało poświadczenia.")
        secret = self._keys[credential_id]
        return hashlib.sha256(secret + salt).digest()


def test_keyring_store_with_in_memory_backend():
    original_keyring = keyring.get_keyring()
    try:
        mem_backend = InMemoryKeyring()
        keyring.set_keyring(mem_backend)

        store = KeyringStore()
        assert store.get("test_acc") is None

        store.set("test_acc", "SekretneHaslo123")
        assert store.get("test_acc") == "SekretneHaslo123"

        store.delete("test_acc")
        assert store.get("test_acc") is None
        # Usunięcie nieistniejącego nie rzuca błędu
        store.delete("test_acc")
    finally:
        keyring.set_keyring(original_keyring)


def test_keyring_store_unavailable():
    original_keyring = keyring.get_keyring()
    try:
        keyring.set_keyring(keyring.backends.fail.Keyring())
        with pytest.raises(SecretStoreUnavailable):
            KeyringStore()
    finally:
        keyring.set_keyring(original_keyring)


def test_encrypted_file_store_roundtrip(tmp_path: Path):
    path = tmp_path / "secrets.json"
    passphrase = "MocnaFrazaRatunkowa123!"

    store = EncryptedFileStore(path, passphrase)
    assert store.get("gmail") is None

    store.set("gmail", "HasloAplikacjiGmail")
    store.set("work", "HasloDoPocztyPracy")

    # Weryfikacja uprawnień 0600
    st_mode = os.stat(path).st_mode
    assert oct(st_mode & 0o777) == "0o600"

    # Weryfikacja braku hasła w pliku otwartym tekstem
    with open(path, "rb") as f:
        raw_bytes = f.read()
    assert b"HasloAplikacjiGmail" not in raw_bytes
    assert b"HasloDoPocztyPracy" not in raw_bytes

    # Ponowne otwarcie tym samym hasłem
    store2 = EncryptedFileStore(path, passphrase)
    assert store2.get("gmail") == "HasloAplikacjiGmail"
    assert store2.get("work") == "HasloDoPocztyPracy"
    assert store2.get("nieistnieje") is None

    # Usunięcie
    store2.delete("gmail")
    assert store2.get("gmail") is None


def test_encrypted_file_store_wrong_passphrase(tmp_path: Path):
    path = tmp_path / "secrets.json"
    store = EncryptedFileStore(path, "Haslo1")
    store.set("acc", "sekret")

    with pytest.raises(SecretStoreError):
        EncryptedFileStore(path, "ZleHaslo2")


def test_encrypted_file_store_corrupted_file(tmp_path: Path):
    path = tmp_path / "secrets.json"
    with open(path, "wb") as f:
        f.write(b"niepoprawny json")

    with pytest.raises(SecretStoreError):
        EncryptedFileStore(path, "Haslo")


def test_fido2_store_two_keys_and_loss_of_one(tmp_path: Path):
    path = tmp_path / "fido2_vault.json"
    dev1 = FakeHmacDevice()
    dev2 = FakeHmacDevice()

    # Inicjalizacja magazynu z kluczem dev1
    store = Fido2Store(path, recovery_passphrase="FrazaRatunkowa", device=dev1)
    store.set("acc1", "WazneHasloFIDO2")

    # Zarejestrowanie drugiego klucza dev2
    store.enroll_device(dev2)

    # Utrata klucza dev1 (tworzymy uszkodzone urządzenie symulujące brak/awarię dev1)
    broken_dev1 = FakeHmacDevice(fail_derive=True)

    # Otwarcie za pomocą klucza dev2
    store_unlocked_with_dev2 = Fido2Store(path, recovery_passphrase="FrazaRatunkowa", device=dev2)
    assert store_unlocked_with_dev2.get("acc1") == "WazneHasloFIDO2"

    # Otwarcie bez urządzeń za pomocą samej frazy ratunkowej
    store_recovery = Fido2Store(path, recovery_passphrase="FrazaRatunkowa", device=None)
    assert store_recovery.get("acc1") == "WazneHasloFIDO2"

    # Zła fraza i brak klucza dev1 rzuca SecretStoreError
    with pytest.raises(SecretStoreError):
        Fido2Store(path, recovery_passphrase="ZlaFrazaRatunkowa", device=broken_dev1)


def test_create_store_factory(tmp_path: Path):
    original_keyring = keyring.get_keyring()
    try:
        keyring.set_keyring(InMemoryKeyring())
        ks = create_store(backend="keyring")
        assert isinstance(ks, KeyringStore)
    finally:
        keyring.set_keyring(original_keyring)

    path = tmp_path / "store.json"
    fs = create_store(backend="file", file_path=path, passphrase="fraza")
    assert isinstance(fs, EncryptedFileStore)

    dev = FakeHmacDevice()
    f2 = create_store(
        backend="fido2",
        file_path=tmp_path / "fido.json",
        passphrase="p",
        fido2_device=dev,
    )
    assert isinstance(f2, Fido2Store)

    with pytest.raises(ValueError):
        create_store(backend="nieznany")


def test_imap_tools_client_enforces_ssl_and_sanitizes():
    # Odmowa połączenia bez SSL
    client_no_ssl = ImapToolsClient(
        host="imap.local",
        port=143,
        username="u@local",
        password="TajneHaslo",
        use_ssl=False,
    )
    with pytest.raises(FetchError, match="Połączenia nieszyfrowane są zabronione"):
        client_no_ssl.get_uidvalidity("INBOX")

    # Maskowanie hasła w błędzie połączenia
    client_ssl = ImapToolsClient(
        host="nieistnieje.local",
        port=993,
        username="u@local",
        password="SuperTajneHasloRegresja",
        use_ssl=True,
    )
    with pytest.raises(FetchError) as exc_info:
        client_ssl.get_uidvalidity("INBOX")
    assert "SuperTajneHasloRegresja" not in str(exc_info.value)


@pytest.fixture(autouse=True)
def _fast_scrypt(monkeypatch):
    """Testy używają słabego scrypt (szybko); produkcyjne n zostaje w module."""
    monkeypatch.setattr(secrets_mod, "SCRYPT_N", 2**10)


def test_production_scrypt_parameters_are_strong():
    import importlib

    fresh = importlib.reload(secrets_mod)
    assert fresh.SCRYPT_N >= 2**17


def test_file_records_kdf_params_and_survives_reload(tmp_path):
    path = tmp_path / "v.json"
    store = secrets_mod.EncryptedFileStore(path, "fraza")
    store.set("acc", "hasło")
    assert '"n": 1024' in path.read_text()
    assert secrets_mod.EncryptedFileStore(path, "fraza").get("acc") == "hasło"


def test_write_is_atomic_and_leaves_no_tmp_file(tmp_path, monkeypatch):
    path = tmp_path / "v.json"
    store = secrets_mod.EncryptedFileStore(path, "fraza")
    store.set("acc", "stare")
    before = path.read_text()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(secrets_mod.os, "replace", boom)
    with pytest.raises(secrets_mod.SecretStoreError):
        store.set("acc", "nowe")
    assert path.read_text() == before  # stary sejf nietknięty
    assert not list(tmp_path.glob("*.tmp"))
