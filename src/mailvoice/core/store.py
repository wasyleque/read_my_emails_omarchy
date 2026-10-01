import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FolderState:
    account: str
    folder: str
    uidvalidity: int
    last_uid: int


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self._create_tables()

    def _create_tables(self):
        cursor = self.connection.cursor()

        # Create seen table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                account TEXT,
                folder TEXT,
                uidvalidity INTEGER,
                uid INTEGER,
                message_id TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                importance INTEGER,
                PRIMARY KEY(account, folder, uidvalidity, uid)
            )
        """)

        # Create folder_state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS folder_state (
                account TEXT,
                folder TEXT,
                uidvalidity INTEGER,
                last_uid INTEGER,
                PRIMARY KEY(account, folder)
            )
        """)

        # Create analysis_attempts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_attempts (
                account TEXT,
                folder TEXT,
                uidvalidity INTEGER,
                uid INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account, folder, uidvalidity, uid)
            )
        """)

        # Migracja tabeli seen jeśli kolumna attempts nie istnieje
        cursor.execute("PRAGMA table_info(seen)")
        seen_cols = [row[1] for row in cursor.fetchall()]
        if "attempts" not in seen_cols:
            cursor.execute("ALTER TABLE seen ADD COLUMN attempts INTEGER DEFAULT 0")

        self.connection.commit()

    def get_last_uid(self, account: str, folder: str, uidvalidity: int) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT last_uid FROM folder_state
            WHERE account = ? AND folder = ? AND uidvalidity = ?
        """,
            (account, folder, uidvalidity),
        )

        result = cursor.fetchone()
        return result[0] if result else 0

    def has_last_uid(self, account: str, folder: str, uidvalidity: int) -> bool:
        """True, jeśli dla folderu zapisano już linię bazową (także 0) przy tym UIDVALIDITY."""
        row = self.connection.execute(
            "SELECT 1 FROM folder_state WHERE account = ? AND folder = ? AND uidvalidity = ?",
            (account, folder, uidvalidity),
        ).fetchone()
        return row is not None

    def set_last_uid(self, account: str, folder: str, uidvalidity: int, last_uid: int) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO folder_state (account, folder, uidvalidity, last_uid)
            VALUES (?, ?, ?, ?)
        """,
            (account, folder, uidvalidity, last_uid),
        )

        self.connection.commit()

    def is_seen(
        self, account: str, folder: str, uidvalidity: int, uid: int, message_id: Optional[str]
    ) -> bool:
        cursor = self.connection.cursor()

        # Check if there's an entry with the exact key
        cursor.execute(
            """
            SELECT 1 FROM seen
            WHERE account = ? AND folder = ? AND uidvalidity = ? AND uid = ?
        """,
            (account, folder, uidvalidity, uid),
        )

        if cursor.fetchone():
            return True

        # Ten sam message_id na tym koncie = już widziany
        if message_id:
            cursor.execute(
                """
                SELECT 1 FROM seen
                WHERE account = ? AND message_id = ?
            """,
                (account, message_id),
            )

            if cursor.fetchone():
                return True

        return False

    def mark_seen(
        self,
        account: str,
        folder: str,
        uidvalidity: int,
        uid: int,
        message_id: Optional[str],
        status: str = "analyzed",
        importance: Optional[int] = None,
    ) -> None:
        # Validate status
        allowed_statuses = {"new", "analyzed", "backlog_declined", "failed", "backlog_pending"}
        if status not in allowed_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of {allowed_statuses}")

        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO seen
                (account, folder, uidvalidity, uid, message_id, status, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (account, folder, uidvalidity, uid, message_id, status, importance),
        )

        self.connection.commit()

    def get_seen_status(
        self, account: str, folder: str, uidvalidity: int, uid: int
    ) -> Optional[str]:
        """Zwraca status z tabeli seen dla podanej wiadomości lub None."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT status FROM seen
            WHERE account = ? AND folder = ? AND uidvalidity = ? AND uid = ?
            """,
            (account, folder, uidvalidity, uid),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else None

    def get_attempts(self, account: str, folder: str, uidvalidity: int, uid: int) -> int:
        """Zwraca liczbę nieudanych prób analizy formatu dla wiadomości."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT attempts FROM analysis_attempts
            WHERE account = ? AND folder = ? AND uidvalidity = ? AND uid = ?
            """,
            (account, folder, uidvalidity, uid),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def increment_attempts(self, account: str, folder: str, uidvalidity: int, uid: int) -> int:
        """Zwiększa i zwraca licznik nieudanych prób analizy dla wiadomości."""
        current = self.get_attempts(account, folder, uidvalidity, uid)
        new_attempts = current + 1
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO analysis_attempts
                (account, folder, uidvalidity, uid, attempts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account, folder, uidvalidity, uid, new_attempts),
        )
        self.connection.commit()
        return new_attempts

    def clear_attempts(self, account: str, folder: str, uidvalidity: int, uid: int) -> None:
        """Czyści licznik prób dla wiadomości."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            DELETE FROM analysis_attempts
            WHERE account = ? AND folder = ? AND uidvalidity = ? AND uid = ?
            """,
            (account, folder, uidvalidity, uid),
        )
        self.connection.commit()

    def close(self):
        if self.connection:
            self.connection.close()
