"""Moduł bezpiecznego przechowywania haseł i sekretów (SecretStore).

Obsługuje:
- KeyringStore (systemowy pęk kluczy)
- EncryptedFileStore (szyfrowany plik AES-256-GCM z kluczem scrypt)
- Fido2Store (opcjonalny magazyn ze sprzętowym kluczem FIDO2 hmac-secret)
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

import keyring
import keyring.backends.fail
import keyring.backends.null
import keyring.errors
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVICE_NAME = "mailvoice"


class SecretStoreError(Exception):
    """Bazowy błąd operacji na magazynie sekretów."""

    pass


class SecretStoreUnavailable(SecretStoreError):
    """Wyjątek rzucany, gdy wybrany backend magazynu jest niedostępny w systemie."""

    pass


class SecretStore(Protocol):
    """Protokół magazynu sekretów dla kont pocztowych."""

    def get(self, account: str) -> str | None:
        """Pobiera sekret dla podanego konta lub None, jeśli nie istnieje."""
        ...

    def set(self, account: str, secret: str) -> None:
        """Zapisuje sekret dla podanego konta."""
        ...

    def delete(self, account: str) -> None:
        """Usuwa sekret dla podanego konta."""
        ...


class KeyringStore:
    """Implementacja SecretStore oparta na systemowym pęku kluczy (keyring)."""

    def __init__(self, service: str = SERVICE_NAME) -> None:
        self.service = service
        self._verify_backend()

    def _verify_backend(self) -> None:
        backend = keyring.get_keyring()
        if (
            isinstance(backend, (keyring.backends.fail.Keyring, keyring.backends.null.Keyring))
            or getattr(backend, "priority", 0) <= 0
        ):
            raise SecretStoreUnavailable(
                "Systemowy keyring jest niedostępny lub nie posiada aktywnego backendu. "
                "Skonfiguruj systemowy pęk kluczy (np. SecretService/Keychain) "
                "lub skorzystaj z EncryptedFileStore."
            )

    def get(self, account: str) -> str | None:
        try:
            return keyring.get_password(self.service, account)
        except Exception as exc:
            raise SecretStoreError(f"Błąd odczytu z keyring dla konta '{account}': {exc}") from exc

    def set(self, account: str, secret: str) -> None:
        try:
            keyring.set_password(self.service, account, secret)
        except Exception as exc:
            raise SecretStoreError(f"Błąd zapisu do keyring dla konta '{account}': {exc}") from exc

    def delete(self, account: str) -> None:
        try:
            keyring.delete_password(self.service, account)
        except keyring.errors.PasswordDeleteError:
            # Hasło nie istniało - operacja idempotentna
            pass
        except Exception as exc:
            raise SecretStoreError(
                f"Błąd usuwania hasła z keyring dla konta '{account}': {exc}"
            ) from exc


SCRYPT_N = 2**17  # ~128 MiB, zapisywane w pliku (stare pliki: 2**14)
_SCRYPT_N_LEGACY = 2**14


def _derive_scrypt_key(passphrase: str, salt: bytes, n: int | None = None) -> bytes:
    """Wyprowadza 32-bajtowy klucz AES-256 z frazy i soli przy użyciu scrypt."""
    n = n or SCRYPT_N
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=n,
        r=8,
        p=1,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    )


def _write_private_atomic(path: Path, payload: dict) -> None:
    """Atomowy zapis JSON z uprawnieniami 0600 (plik tymczasowy + fsync + os.replace)."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class EncryptedFileStore:
    """Magazyn sekretów w szyfrowanym pliku JSON z uprawnieniami 0600 (AES-256-GCM + scrypt)."""

    def __init__(self, path: str | Path, passphrase: str) -> None:
        if not passphrase:
            raise SecretStoreError("Fraza szyfrująca nie może być pusta.")
        self.path = Path(path)
        self.passphrase = passphrase
        self._cache: dict[str, str] = {}
        self._salt: bytes | None = None
        self._n = SCRYPT_N
        self._key: bytes | None = None
        self._load_or_init()

    def _load_or_init(self) -> None:
        if not self.path.exists():
            self._salt = os.urandom(16)
            self._cache = {}
            self._key = _derive_scrypt_key(self.passphrase, self._salt, self._n)
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)

            salt = base64.b64decode(data["salt"])
            nonce = base64.b64decode(data["nonce"])
            ciphertext = base64.b64decode(data["ciphertext"])
            self._salt = salt
            self._n = int(data.get("kdf", {}).get("n", _SCRYPT_N_LEGACY))

            key = _derive_scrypt_key(self.passphrase, salt, self._n)
            self._key = key
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            self._cache = json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, json.JSONDecodeError, InvalidTag) as exc:
            raise SecretStoreError(
                "Nie udało się odszyfrować magazynu sekretów (błędna fraza lub uszkodzony plik)."
            ) from exc
        except Exception as exc:
            raise SecretStoreError(f"Błąd odczytu pliku magazynu sekretów: {exc}") from exc

    def _save(self) -> None:
        if self._salt is None:
            self._salt = os.urandom(16)

        if self._key is None:
            self._key = _derive_scrypt_key(self.passphrase, self._salt, self._n)
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        plaintext = json.dumps(self._cache).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)

        payload = {
            "version": 1,
            "kdf": {"name": "scrypt", "n": self._n, "r": 8, "p": 1},
            "salt": base64.b64encode(self._salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

        try:
            _write_private_atomic(self.path, payload)
        except Exception as exc:
            raise SecretStoreError(f"Błąd zapisu do pliku sekretów: {exc}") from exc

    def get(self, account: str) -> str | None:
        return self._cache.get(account)

    def set(self, account: str, secret: str) -> None:
        self._cache[account] = secret
        self._save()

    def delete(self, account: str) -> None:
        if account in self._cache:
            del self._cache[account]
            self._save()


class HmacSecretDevice(Protocol):
    """Protokół sprzętowego urządzenia FIDO2 obsługującego rozszerzenie hmac-secret."""

    def enroll(self) -> bytes:
        """Rejestruje klucz i zwraca unikalny credential_id."""
        ...

    def derive(self, credential_id: bytes, salt: bytes) -> bytes:
        """Wyprowadza 32-bajtowy sekret na podstawie credential_id i soli."""
        ...


class RealHmacSecretDevice:
    """Implementacja FIDO2 hmac-secret na bibliotece python-fido2.

    Wymaga testu na sprzęcie i na Windowsie (issue #4).
    """

    def __init__(self) -> None:
        try:
            import fido2  # noqa: F401
        except ImportError as exc:
            raise SecretStoreUnavailable(
                "Biblioteka python-fido2 nie jest zainstalowana. Zainstaluj `pip install .[fido2]`."
            ) from exc

    def enroll(self) -> bytes:
        raise NotImplementedError(
            "Rejestracja na fizycznym sprzęcie FIDO2 wymaga testu na Windows/Linux (issue #4)."
        )

    def derive(self, credential_id: bytes, salt: bytes) -> bytes:
        raise NotImplementedError(
            "Wyprowadzanie klucza hmac-secret wymaga testu na sprzęcie (issue #4)."
        )


class Fido2Store:
    """Magazyn sekretów chroniony kluczem FIDO2 (hmac-secret) z awaryjną frazą ratunkową."""

    def __init__(
        self,
        path: str | Path,
        recovery_passphrase: str,
        device: HmacSecretDevice | None = None,
    ) -> None:
        self.path = Path(path)
        self.recovery_passphrase = recovery_passphrase
        self._device = device
        self._cache: dict[str, str] = {}
        self._data_key: bytes | None = None
        self._devices_data: list[dict[str, str]] = []
        self._recovery_salt: bytes | None = None
        self._recovery_n = SCRYPT_N
        self._recovery_wrapped_key: bytes | None = None
        self._recovery_nonce: bytes | None = None

        if self.path.exists():
            self._load_metadata()
            self._unlock()
        else:
            self._init_new()

    def _init_new(self) -> None:
        self._data_key = os.urandom(32)
        self._cache = {}
        self._recovery_salt = os.urandom(16)
        rec_key = _derive_scrypt_key(
            self.recovery_passphrase, self._recovery_salt, self._recovery_n
        )
        self._recovery_nonce = os.urandom(12)
        self._recovery_wrapped_key = AESGCM(rec_key).encrypt(
            self._recovery_nonce, self._data_key, None
        )

        if self._device is not None:
            self.enroll_device(self._device)
        else:
            self._save()

    def _load_metadata(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._devices_data = data.get("devices", [])
            self._recovery_salt = base64.b64decode(data["recovery"]["salt"])
            self._recovery_n = int(data["recovery"].get("n", _SCRYPT_N_LEGACY))
            self._recovery_nonce = base64.b64decode(data["recovery"]["nonce"])
            self._recovery_wrapped_key = base64.b64decode(data["recovery"]["wrapped_key"])
        except Exception as exc:
            raise SecretStoreError(f"Błąd odczytu metadanych FIDO2: {exc}") from exc

    def _unlock(self) -> None:
        # Próba odblokowania urządzeniem
        if self._device is not None:
            for dev_entry in self._devices_data:
                try:
                    cred_id = base64.b64decode(dev_entry["credential_id"])
                    salt = base64.b64decode(dev_entry["salt"])
                    nonce = base64.b64decode(dev_entry["nonce"])
                    wrapped_key = base64.b64decode(dev_entry["wrapped_key"])

                    dev_key = self._device.derive(cred_id, salt)
                    self._data_key = AESGCM(dev_key).decrypt(nonce, wrapped_key, None)
                    self._load_secrets()
                    return
                except Exception:
                    continue

        # Próba odblokowania frazą ratunkową
        if self._recovery_salt and self._recovery_nonce and self._recovery_wrapped_key:
            try:
                rec_key = _derive_scrypt_key(
                    self.recovery_passphrase, self._recovery_salt, self._recovery_n
                )
                self._data_key = AESGCM(rec_key).decrypt(
                    self._recovery_nonce, self._recovery_wrapped_key, None
                )
                self._load_secrets()
                return
            except Exception as exc:
                raise SecretStoreError(
                    "Nie udało się odblokować magazynu FIDO2 (zły klucz sprzętowy lub fraza)."
                ) from exc

        raise SecretStoreError("Brak metody odblokowania magazynu FIDO2.")

    def _load_secrets(self) -> None:
        if self._data_key is None:
            raise SecretStoreError("Magazyn FIDO2 jest zablokowany.")
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        nonce = base64.b64decode(data["data_nonce"])
        ciphertext = base64.b64decode(data["data_ciphertext"])
        plaintext = AESGCM(self._data_key).decrypt(nonce, ciphertext, None)
        self._cache = json.loads(plaintext.decode("utf-8"))

    def enroll_device(self, device: HmacSecretDevice) -> bytes:
        """Rejestruje nowe urządzenie FIDO2 w magazynie i aktualizuje plik."""
        if self._data_key is None:
            raise SecretStoreError("Magazyn musi być odblokowany, aby zarejestrować klucz.")

        cred_id = device.enroll()
        salt = os.urandom(32)
        dev_key = device.derive(cred_id, salt)
        nonce = os.urandom(12)
        wrapped_key = AESGCM(dev_key).encrypt(nonce, self._data_key, None)

        self._devices_data.append(
            {
                "credential_id": base64.b64encode(cred_id).decode("ascii"),
                "salt": base64.b64encode(salt).decode("ascii"),
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "wrapped_key": base64.b64encode(wrapped_key).decode("ascii"),
            }
        )
        self._save()
        return cred_id

    def _save(self) -> None:
        if (
            self._data_key is None
            or self._recovery_salt is None
            or self._recovery_nonce is None
            or self._recovery_wrapped_key is None
        ):
            raise SecretStoreError("Nie można zapisać zablokowanego magazynu FIDO2.")

        data_nonce = os.urandom(12)
        plaintext = json.dumps(self._cache).encode("utf-8")
        data_ciphertext = AESGCM(self._data_key).encrypt(data_nonce, plaintext, None)

        payload = {
            "version": 1,
            "devices": self._devices_data,
            "recovery": {
                "n": self._recovery_n,
                "salt": base64.b64encode(self._recovery_salt).decode("ascii"),
                "nonce": base64.b64encode(self._recovery_nonce).decode("ascii"),
                "wrapped_key": base64.b64encode(self._recovery_wrapped_key).decode("ascii"),
            },
            "data_nonce": base64.b64encode(data_nonce).decode("ascii"),
            "data_ciphertext": base64.b64encode(data_ciphertext).decode("ascii"),
        }

        try:
            _write_private_atomic(self.path, payload)
        except Exception as exc:
            raise SecretStoreError(f"Błąd zapisu magazynu FIDO2: {exc}") from exc

    def get(self, account: str) -> str | None:
        return self._cache.get(account)

    def set(self, account: str, secret: str) -> None:
        self._cache[account] = secret
        self._save()

    def delete(self, account: str) -> None:
        if account in self._cache:
            del self._cache[account]
            self._save()


def create_store(
    config: Any = None,
    backend: str = "keyring",
    file_path: str | Path | None = None,
    passphrase: str | None = None,
    fido2_device: HmacSecretDevice | None = None,
) -> SecretStore:
    """Fabryka magazynu sekretów.

    Domyślnie używa systemowego keyring. Jeśli jest niedostępny, rzuca
    SecretStoreUnavailable z instrukcją konfiguracji.
    """
    if backend == "keyring":
        return KeyringStore()

    if backend == "file":
        if not file_path or not passphrase:
            raise ValueError("EncryptedFileStore wymaga podania file_path oraz passphrase.")
        return EncryptedFileStore(file_path, passphrase)

    if backend == "fido2":
        if not file_path or not passphrase:
            raise ValueError("Fido2Store wymaga podania file_path oraz awaryjnej passphrase.")
        device = fido2_device or RealHmacSecretDevice()
        return Fido2Store(file_path, recovery_passphrase=passphrase, device=device)

    raise ValueError(f"Nieznany backend magazynu sekretów: '{backend}'")
