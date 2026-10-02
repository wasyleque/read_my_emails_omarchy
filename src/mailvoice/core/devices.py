"""Zarządzanie sparowanymi urządzeniami mobilnymi (Android) i sesjami parowania."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Alfabet kodu parowania: 30 znaków bez mylących znaków (brak 0, O, 1, I)
PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class DeviceError(Exception):
    """Bazowy błąd operacji na urządzeniach."""


class PairingError(DeviceError):
    """Błąd parowania urządzenia."""


class PairingExpiredError(PairingError):
    """Kod parowania wygasł."""


class PairingLockedError(PairingError):
    """Sesja parowania została zablokowana po zbyt wielu błędnych próbach."""


class DeviceLimitError(DeviceError):
    """Osiągnięto maksymalną liczbę sparowanych urządzeń."""


@dataclass(frozen=True)
class PairedDevice:
    """Informacje o sparowanym telefonie."""

    id: str
    name: str
    token_hash: str
    created_at: str
    last_seen: str
    revoked: bool


class PairingSession:
    """Jednorazowa sesja parowania nowego urządzenia."""

    def __init__(
        self,
        code: str,
        timeout_s: float = 120.0,
        max_attempts: int = 5,
        created_at: float | None = None,
    ) -> None:
        self.code = code.upper().strip()
        self.created_at = created_at if created_at is not None else time.time()
        self.expires_at = self.created_at + timeout_s
        self.max_attempts = max_attempts
        self.attempts = 0
        self.is_used = False
        self.is_locked = False
        self._lock = threading.Lock()

    @property
    def remaining_seconds(self) -> int:
        now = time.time()
        return max(0, int(self.expires_at - now))

    def is_valid(self, now: float | None = None) -> bool:
        current_time = now if now is not None else time.time()
        with self._lock:
            if self.is_used or self.is_locked:
                return False
            return current_time < self.expires_at

    def verify_and_consume(self, candidate_code: str, now: float | None = None) -> bool:
        """Sprawdza kod w stałym czasie i unieważnia sesję w razie sukcesu lub blokady."""
        current_time = now if now is not None else time.time()
        with self._lock:
            if self.is_used or self.is_locked:
                return False
            if current_time >= self.expires_at:
                return False

            clean_candidate = candidate_code.strip().upper().replace("-", "").replace(" ", "")
            match = hmac.compare_digest(self.code, clean_candidate)

            if match:
                self.is_used = True
                return True

            self.attempts += 1
            if self.attempts >= self.max_attempts:
                self.is_locked = True
            return False


class DeviceManager:
    """Baza danych i zarządzanie sparowanymi urządzeniami w SQLite."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.path = Path(db_path)
        self._memory = str(db_path) == ":memory:"
        self._local = threading.local()
        self._open_connections: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        self._shared: sqlite3.Connection | None = None
        if self._memory:
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)

        self._active_session: PairingSession | None = None
        self._session_lock = threading.Lock()

        self._init_db()

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        with self._conns_lock:
            self._open_connections.append(conn)
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        if self._shared is not None:
            return self._shared
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._open_connection()
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paired_devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_paired_devices_token_hash
            ON paired_devices(token_hash)
        """)
        self.connection.commit()

    def close(self) -> None:
        with self._conns_lock:
            for conn in self._open_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._open_connections.clear()
        if self._shared is not None:
            try:
                self._shared.close()
            except Exception:
                pass
            self._shared = None

    def start_pairing_session(
        self,
        timeout_s: float = 120.0,
        code_length: int = 6,
    ) -> PairingSession:
        """Tworzy i aktywuje nową sesję parowania z losowym czytelnym kodem."""
        code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(code_length))
        session = PairingSession(code=code, timeout_s=timeout_s)
        with self._session_lock:
            self._active_session = session
        return session

    def get_active_session(self) -> PairingSession | None:
        """Zwraca aktywną sesję parowania, o ile jest nadal ważna."""
        with self._session_lock:
            if self._active_session and self._active_session.is_valid():
                return self._active_session
            return None

    def cancel_pairing_session(self) -> None:
        """Anuluje aktywną sesję parowania."""
        with self._session_lock:
            self._active_session = None

    def pair_device(
        self,
        code: str,
        device_name: str,
        max_devices: int = 5,
    ) -> tuple[str, str]:
        """Weryfikuje kod parowania i rejestruje nowe urządzenie.

        Zwraca parę (device_id, token).
        Token jest generowany jako 32 bajty bezpiecznej losowości.
        W bazie zapisywany jest wyłącznie jego skrót SHA-256 (token nigdy nie trafia
        do bazy w postaci jawnej).
        """
        with self._session_lock:
            session = self._active_session

        if not session:
            raise PairingError("Brak aktywnej sesji parowania. Otwórz okno parowania w programie.")

        if session.is_locked:
            raise PairingLockedError(
                "Sesja parowania została zablokowana po zbyt wielu błędnych próbach."
            )

        if not session.is_valid():
            raise PairingExpiredError("Kod parowania wygasł. Wygeneruj nowy kod.")

        valid = session.verify_and_consume(code)
        if not valid:
            if session.is_locked:
                raise PairingLockedError(
                    "Zbyt wiele błędnych prób. Sesja parowania została zablokowana."
                )
            remaining = session.max_attempts - session.attempts
            raise PairingError(f"Niepoprawny kod parowania. Pozostało prób: {remaining}")

        # Sprawdzenie limitu aktywnych urządzeń
        active_devices = self.list_devices(include_revoked=False)
        if len(active_devices) >= max_devices:
            raise DeviceLimitError(
                f"Osiągnięto limit {max_devices} sparowanych urządzeń. Usuń nieużywane urządzenie."
            )

        # Generowanie poświadczeń
        device_id = f"dev_{secrets.token_hex(8)}"
        clean_name = device_name.strip() or "Telefon Android"
        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc).isoformat()

        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO paired_devices (id, name, token_hash, created_at, last_seen, revoked)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (device_id, clean_name, token_hash, now, now),
        )
        self.connection.commit()

        # Po pomyślnym sparowaniu zamykamy sesję
        with self._session_lock:
            self._active_session = None

        return device_id, token

    def verify_token(self, token: str) -> Optional[PairedDevice]:
        """Weryfikuje token urządzenia w stałym czasie i aktualizuje czas last_seen."""
        if not token or len(token) < 16:
            return None

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, token_hash, created_at, last_seen, revoked
            FROM paired_devices
            WHERE revoked = 0
            """
        )
        rows = cursor.fetchall()

        matched_device: PairedDevice | None = None
        for row in rows:
            # Porównanie w stałym czasie dla zabezpieczenia przed atakiem timing attack
            if hmac.compare_digest(row[2], token_hash):
                matched_device = PairedDevice(
                    id=row[0],
                    name=row[1],
                    token_hash=row[2],
                    created_at=row[3],
                    last_seen=row[4],
                    revoked=bool(row[5]),
                )
                break

        if matched_device:
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "UPDATE paired_devices SET last_seen = ? WHERE id = ?",
                (now, matched_device.id),
            )
            self.connection.commit()

        return matched_device

    def list_devices(self, include_revoked: bool = False) -> list[PairedDevice]:
        """Zwraca listę sparowanych urządzeń."""
        cursor = self.connection.cursor()
        if include_revoked:
            cursor.execute(
                """
                SELECT id, name, token_hash, created_at, last_seen, revoked
                FROM paired_devices ORDER BY created_at ASC
                """
            )
        else:
            cursor.execute(
                """
                SELECT id, name, token_hash, created_at, last_seen, revoked
                FROM paired_devices WHERE revoked = 0 ORDER BY created_at ASC
                """
            )
        rows = cursor.fetchall()
        return [
            PairedDevice(
                id=r[0],
                name=r[1],
                token_hash=r[2],
                created_at=r[3],
                last_seen=r[4],
                revoked=bool(r[5]),
            )
            for r in rows
        ]

    def get_device(self, device_id: str) -> Optional[PairedDevice]:
        """Pobiera urządzenie po identyfikatorze."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, token_hash, created_at, last_seen, revoked
            FROM paired_devices WHERE id = ?
            """,
            (device_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return PairedDevice(
            id=row[0],
            name=row[1],
            token_hash=row[2],
            created_at=row[3],
            last_seen=row[4],
            revoked=bool(row[5]),
        )

    def revoke_device(self, device_id: str) -> bool:
        """Odwołuje dostęp dla wskazanego urządzenia (status revoked=1)."""
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE paired_devices SET revoked = 1 WHERE id = ?",
            (device_id,),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def delete_device(self, device_id: str) -> bool:
        """Całkowicie usuwa wpis urządzenia z bazy danych."""
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM paired_devices WHERE id = ?", (device_id,))
        self.connection.commit()
        return cursor.rowcount > 0
