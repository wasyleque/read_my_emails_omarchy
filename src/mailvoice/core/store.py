import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


@dataclass
class FolderState:
    account: str
    folder: str
    uidvalidity: int
    last_uid: int


@dataclass(frozen=True)
class MailIndexRecord:
    """Wpis indeksu wiadomości w bazie SQLite (bez pełnej treści)."""

    account: str
    folder: str
    uidvalidity: int
    uid: int
    message_id: str | None
    thread_key: str
    date: str | None
    sender: str
    recipients: str
    subject: str
    importance: int | None
    why: str | None
    summary: str | None


@dataclass(frozen=True)
class TopicDigestCacheRecord:
    """Zapis pamięci podręcznej podsumowania wątku."""

    thread_key: str
    last_mail_date: str | None
    mail_count: int
    title: str
    why: str
    status: str
    who_to_whom: list[str]
    cached_at: str


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = Path(path)
        self.has_fts = False
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

        # Create mail_index table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mail_index (
                account TEXT NOT NULL,
                folder TEXT NOT NULL,
                uidvalidity INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                message_id TEXT,
                thread_key TEXT NOT NULL,
                date TEXT,
                sender TEXT NOT NULL,
                recipients TEXT NOT NULL,
                subject TEXT NOT NULL,
                importance INTEGER,
                why TEXT,
                summary TEXT,
                PRIMARY KEY(account, folder, uidvalidity, uid)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_mail_index_thread ON mail_index(thread_key)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_mail_index_date ON mail_index(date)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_mail_index_sender ON mail_index(sender)"
        )

        # Create topic_digest_cache table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS topic_digest_cache (
                thread_key TEXT PRIMARY KEY,
                last_mail_date TEXT,
                mail_count INTEGER NOT NULL,
                title TEXT NOT NULL,
                why TEXT NOT NULL,
                status TEXT NOT NULL,
                who_to_whom TEXT NOT NULL,
                cached_at TEXT NOT NULL
            )
        """)

        # Create contacts and contact_addresses tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contact_addresses (
                contact_id INTEGER NOT NULL,
                address TEXT UNIQUE NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_contact_addresses_addr ON contact_addresses(address)"
        )
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contact_card_cache (
                contact_id INTEGER PRIMARY KEY,
                last_mail_date TEXT,
                mail_count INTEGER NOT NULL,
                relationship_hint TEXT NOT NULL,
                why_it_matters TEXT NOT NULL,
                cached_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            )
        """)

        # Create mail_fts table if FTS5 is available
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS mail_fts USING fts5(
                    sender,
                    recipients,
                    subject,
                    summary,
                    why,
                    account UNINDEXED,
                    folder UNINDEXED,
                    uidvalidity UNINDEXED,
                    uid UNINDEXED,
                    date UNINDEXED
                )
            """)
            cursor.execute("SELECT COUNT(*) FROM mail_fts")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT OR REPLACE INTO mail_fts
                    (sender, recipients, subject, summary, why, account, folder,
                     uidvalidity, uid, date)
                    SELECT sender, recipients, subject, coalesce(summary, ''),
                           coalesce(why, ''), account, folder, uidvalidity, uid,
                           coalesce(date, '')
                    FROM mail_index
                """)
            self.has_fts = True
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            self.has_fts = False

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

    def save_mail_index(self, record: MailIndexRecord) -> None:
        """Zapisuje lub aktualizuje wpis w indeksie wiadomości."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO mail_index
                (account, folder, uidvalidity, uid, message_id, thread_key,
                 date, sender, recipients, subject, importance, why, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.account,
                record.folder,
                record.uidvalidity,
                record.uid,
                record.message_id,
                record.thread_key,
                record.date,
                record.sender,
                record.recipients,
                record.subject,
                record.importance,
                record.why,
                record.summary,
            ),
        )

        if getattr(self, "has_fts", False):
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO mail_fts
                    (sender, recipients, subject, summary, why, account, folder,
                     uidvalidity, uid, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.sender,
                        record.recipients,
                        record.subject,
                        record.summary or "",
                        record.why or "",
                        record.account,
                        record.folder,
                        record.uidvalidity,
                        record.uid,
                        record.date or "",
                    ),
                )
            except sqlite3.Error:
                pass

        self.connection.commit()

    def get_mail_index(
        self, account: str, folder: str, uidvalidity: int, uid: int
    ) -> MailIndexRecord | None:
        """Pobiera wpis z indeksu dla podanego klucza."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT account, folder, uidvalidity, uid, message_id, thread_key,
                   date, sender, recipients, subject, importance, why, summary
            FROM mail_index
            WHERE account = ? AND folder = ? AND uidvalidity = ? AND uid = ?
            """,
            (account, folder, uidvalidity, uid),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return MailIndexRecord(*row)

    def get_records_for_thread(self, thread_key: str) -> list[MailIndexRecord]:
        """Zwraca wszystkie wiadomości powiązane z danym wątkiem, posortowane chronologicznie."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT account, folder, uidvalidity, uid, message_id, thread_key,
                   date, sender, recipients, subject, importance, why, summary
            FROM mail_index
            WHERE thread_key = ?
            ORDER BY date ASC, uid ASC
            """,
            (thread_key,),
        )
        return [MailIndexRecord(*row) for row in cursor.fetchall()]

    def get_all_indexed_records(
        self, since: str | None = None, until: str | None = None
    ) -> list[MailIndexRecord]:
        """Zwraca wpisy z indeksu z opcjonalnym filtrem zakresu dat ISO 8601."""
        query = (
            "SELECT account, folder, uidvalidity, uid, message_id, thread_key, "
            "date, sender, recipients, subject, importance, why, summary "
            "FROM mail_index"
        )
        params: list[str] = []
        conditions: list[str] = []

        if since:
            conditions.append("date >= ?")
            params.append(since)
        if until:
            conditions.append("date <= ?")
            params.append(until)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY date ASC, uid ASC"

        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return [MailIndexRecord(*row) for row in cursor.fetchall()]

    def purge_older_than(self, days: int, now: datetime | None = None) -> int:
        """Usuwa wpisy indeksu starsze niż podana liczba dni."""
        if days < 1:
            return 0
        ref_time = now or datetime.now(timezone.utc)
        cutoff_date = (ref_time - timedelta(days=days)).isoformat()
        cursor = self.connection.cursor()
        cursor.execute(
            "DELETE FROM mail_index WHERE date IS NOT NULL AND date < ?",
            (cutoff_date,),
        )
        deleted = cursor.rowcount
        self.connection.commit()
        return deleted

    def get_topic_digest_cache(self, thread_key: str) -> TopicDigestCacheRecord | None:
        """Pobiera zapis podręczny podsumowania wątku."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT thread_key, last_mail_date, mail_count, title, why,
                   status, who_to_whom, cached_at
            FROM topic_digest_cache
            WHERE thread_key = ?
            """,
            (thread_key,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return TopicDigestCacheRecord(
            thread_key=row[0],
            last_mail_date=row[1],
            mail_count=row[2],
            title=row[3],
            why=row[4],
            status=row[5],
            who_to_whom=json.loads(row[6]) if row[6] else [],
            cached_at=row[7],
        )

    def save_topic_digest_cache(
        self,
        thread_key: str,
        last_mail_date: str | None,
        mail_count: int,
        title: str,
        why: str,
        status: str,
        who_to_whom: list[str],
        cached_at: str | None = None,
    ) -> None:
        """Zapisuje lub aktualizuje podsumowanie wątku w pamięci podręcznej."""
        c_at = cached_at or datetime.now(timezone.utc).isoformat()
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO topic_digest_cache
            (thread_key, last_mail_date, mail_count, title, why, status, who_to_whom, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_key,
                last_mail_date,
                mail_count,
                title,
                why,
                status,
                json.dumps(who_to_whom),
                c_at,
            ),
        )
        self.connection.commit()

    def search_candidates(
        self,
        keywords: list[str],
        senders: list[str] | None = None,
        since: str | None = None,
        limit: int = 20,
    ) -> list[MailIndexRecord]:
        """Szuka kandydatów w indeksie za pomocą FTS5 lub zapasowo przez LIKE."""
        cur = self.connection.cursor()
        senders = senders or []
        records: list[MailIndexRecord] = []

        # 1. Próba wyszukiwania FTS5
        if getattr(self, "has_fts", False):
            tokens = []
            for s in senders:
                clean_s = "".join(c for c in s if c.isalnum() or c in "@.")
                if clean_s:
                    tokens.append(f'"{clean_s}"')
            for kw in keywords:
                clean_k = "".join(c for c in kw if c.isalnum())
                if clean_k:
                    tokens.append(f'"{clean_k}"')

            if tokens:
                fts_query = " OR ".join(tokens)
                sql = (
                    "SELECT account, folder, uidvalidity, uid "
                    "FROM mail_fts WHERE mail_fts MATCH ? "
                )
                params: list[str] = [fts_query]
                if since:
                    sql += "AND date >= ? "
                    params.append(since)
                sql += "ORDER BY rank LIMIT ?"
                params.append(str(limit))

                try:
                    cur.execute(sql, params)
                    keys = cur.fetchall()
                    for acc, fld, uv, u in keys:
                        rec = self.get_mail_index(acc, fld, uv, u)
                        if rec:
                            records.append(rec)
                    if records:
                        return records
                except sqlite3.Error:
                    pass

        # 2. Fallback LIKE (gdy brak FTS5 lub FTS5 nie zwrócił wyników)
        terms = [s for s in senders if s.strip()] + [k for k in keywords if k.strip()]
        if not terms:
            return self.get_all_indexed_records(since=since)[:limit]

        conditions = []
        params = []
        for term in terms:
            like_term = f"%{term}%"
            conditions.append(
                "(sender LIKE ? OR recipients LIKE ? OR subject LIKE ? "
                "OR summary LIKE ? OR why LIKE ?)"
            )
            params.extend([like_term] * 5)

        sql = (
            "SELECT account, folder, uidvalidity, uid, message_id, thread_key, "
            "date, sender, recipients, subject, importance, why, summary "
            "FROM mail_index WHERE (" + " OR ".join(conditions) + ")"
        )
        if since:
            sql += " AND date >= ?"
            params.append(since)
        sql += " ORDER BY date DESC LIMIT ?"
        params.append(str(limit))

        cur.execute(sql, params)
        return [MailIndexRecord(*row) for row in cur.fetchall()]

    def close(self):
        if self.connection:
            self.connection.close()
