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
        allowed_statuses = {"new", "analyzed", "backlog_declined"}
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

    def close(self):
        if self.connection:
            self.connection.close()
