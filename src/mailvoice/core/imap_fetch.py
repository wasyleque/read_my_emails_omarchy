"""Moduł pobierania poczty przez IMAP (tylko odczyt, BODY.PEEK, mark_seen=False)."""

from datetime import date, timedelta
from typing import Protocol, Sequence

from imap_tools import A, MailBox

from mailvoice.core.mailparse import ParsedMail, parse_raw
from mailvoice.core.providers import get_sent_folder_candidates
from mailvoice.core.store import Store


class FetchError(Exception):
    """Wyjątek rzucany przy błędach komunikacji IMAP lub autoryzacji."""

    pass


class MailboxClient(Protocol):
    """Protokół klienta pocztowego oddzielający transport IMAP od logiki biznesowej."""

    def get_uidvalidity(self, folder: str) -> int:
        """Pobiera UIDVALIDITY danego folderu."""
        ...

    def get_uids_greater_than(self, folder: str, min_uid: int) -> list[int]:
        """Pobiera posortowaną rosnąco listę UID większych niż min_uid."""
        ...

    def get_uids_since(self, folder: str, since_date: date) -> list[int]:
        """Pobiera listę UID wiadomości od podanej daty."""
        ...

    def get_unseen_uids(self, folder: str, since_date: date) -> list[int]:
        """Pobiera listę UID wiadomości nieprzeczytanych (UNSEEN) od podanej daty."""
        ...

    def fetch_raw_batch(self, folder: str, uids: Sequence[int]) -> list[tuple[int, bytes]]:
        """Pobiera surową zawartość RFC822 dla wskazanych UID bez zmiany flag na serwerze."""
        ...

    def get_sent_message_ids(self, folder: str, since_date: date) -> list[str]:
        """Pobiera nagłówki Message-ID wiadomości wysłanych od podanej daty."""
        ...

    def close(self) -> None:
        """Zamyka połączenie ze skrzynką pocztową."""
        ...


class ImapToolsClient:
    """Implementacja MailboxClient oparta na bibliotece imap-tools."""

    def __init__(
        self,
        host: str,
        port: int = 993,
        username: str = "",
        password: str = "",
        use_ssl: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.use_ssl = use_ssl
        self.timeout = timeout
        self._mailbox: MailBox | None = None

    def _sanitize_message(self, message: str) -> str:
        """Usuwa hasło z komunikatów o błędach przed ich zalogowaniem/zgłoszeniem."""
        if self._password and self._password in message:
            return message.replace(self._password, "******")
        return message

    def _get_mailbox(self) -> MailBox:
        """Pobiera lub tworzy aktywne połączenie z serwerem IMAP."""
        if self._mailbox is not None:
            return self._mailbox

        if not self.use_ssl:
            raise FetchError(
                "Połączenia nieszyfrowane są zabronione. Wymagane jest szyfrowanie TLS/SSL."
            )

        try:
            mailbox = MailBox(self.host, self.port, timeout=self.timeout)
            mailbox.login(self.username, self._password)
            self._mailbox = mailbox
            return self._mailbox
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd połączenia/logowania do konta {self.username}@{self.host}: {sanitized}"
            ) from None

    def get_uidvalidity(self, folder: str) -> int:
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            status = mailbox.folder.status(folder)
            uidvalidity = status.get("UIDVALIDITY", 0)
            return int(uidvalidity)
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd pobierania UIDVALIDITY dla folderu '{folder}': {sanitized}"
            ) from None

    def get_uids_greater_than(self, folder: str, min_uid: int) -> list[int]:
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            if min_uid > 0:
                criteria = A(uid=f"{min_uid + 1}:*")
            else:
                criteria = A("ALL")
            uid_strings = mailbox.uids(criteria)
            uids = [int(u) for u in uid_strings if u.isdigit()]
            return sorted(u for u in uids if u > min_uid)
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(f"Błąd pobierania UID dla folderu '{folder}': {sanitized}") from None

    def get_uids_since(self, folder: str, since_date: date) -> list[int]:
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            criteria = A(date_gte=since_date)
            uid_strings = mailbox.uids(criteria)
            uids = [int(u) for u in uid_strings if u.isdigit()]
            return sorted(uids)
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd pobierania UID od daty dla folderu '{folder}': {sanitized}"
            ) from None

    def get_unseen_uids(self, folder: str, since_date: date) -> list[int]:
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            criteria = A(seen=False, date_gte=since_date)
            uid_strings = mailbox.uids(criteria)
            uids = [int(u) for u in uid_strings if u.isdigit()]
            return sorted(uids)
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd pobierania nieprzeczytanych UID dla folderu '{folder}': {sanitized}"
            ) from None

    def fetch_raw_batch(self, folder: str, uids: Sequence[int]) -> list[tuple[int, bytes]]:
        if not uids:
            return []
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            uid_str_list = [str(u) for u in uids]
            results: list[tuple[int, bytes]] = []
            for msg in mailbox.fetch(
                uid_list=uid_str_list,
                mark_seen=False,
                bulk=True,
            ):
                results.append((int(msg.uid), msg.obj.as_bytes()))
            return results
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd pobierania wiadomości z folderu '{folder}': {sanitized}"
            ) from None

    def get_sent_message_ids(self, folder: str, since_date: date) -> list[str]:
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            criteria = A(date_gte=since_date)
            message_ids: list[str] = []
            for msg in mailbox.fetch(
                criteria=criteria,
                mark_seen=False,
                headers_only=True,
                bulk=True,
            ):
                mid = msg.headers.get("message-id", ())
                if mid:
                    val = mid[0] if isinstance(mid, (list, tuple)) else str(mid)
                    message_ids.append(val)
            return message_ids
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd pobierania wiadomości z folderu wysłanych '{folder}': {sanitized}"
            ) from None

    def close(self) -> None:
        if self._mailbox is not None:
            try:
                self._mailbox.logout()
            except Exception:
                pass
            finally:
                self._mailbox = None


def normalize_message_id(message_id: str | None) -> str:
    """Ujednolica format Message-ID do postaci w nawiasach ostrokątnych <...>."""
    if not message_id:
        return ""
    clean = message_id.strip()
    if not clean:
        return ""
    if not clean.startswith("<"):
        clean = f"<{clean}"
    if not clean.endswith(">"):
        clean = f"{clean}>"
    return clean


def fetch_new(
    client: MailboxClient,
    store: Store,
    account: str,
    folder: str,
) -> list[tuple[int, ParsedMail]]:
    """Pobiera nowe wiadomości (UID > last_uid) dla danego folderu.

    Nie oznacza wiadomości jako seen ani nie przesuwa last_uid (to zadanie commit_progress).
    """
    uidvalidity = client.get_uidvalidity(folder)
    last_uid = store.get_last_uid(account, folder, uidvalidity)
    candidate_uids = client.get_uids_greater_than(folder, last_uid)

    # Wstępna filtracja po UID znanym z bazy seen
    unseen_uids = [
        u for u in candidate_uids if not store.is_seen(account, folder, uidvalidity, u, None)
    ]
    if not unseen_uids:
        return []

    raw_items = client.fetch_raw_batch(folder, unseen_uids)
    results: list[tuple[int, ParsedMail]] = []

    for uid, raw_bytes in raw_items:
        parsed = parse_raw(raw_bytes)
        # Pomijamy, jeśli ten sam message_id był już widziany w tym koncie
        if store.is_seen(account, folder, uidvalidity, uid, parsed.message_id):
            continue
        results.append((uid, parsed))

    return results


def fetch_backlog(
    client: MailboxClient,
    store: Store,
    account: str,
    folder: str,
    days: int = 30,
) -> list[tuple[int, ParsedMail]]:
    """Pobiera nieprzeczytane wiadomości z ostatnich N dni (zaległości poniżej last_uid).

    Wiadomości nie są oznaczane jako seen w tej funkcji.
    """
    uidvalidity = client.get_uidvalidity(folder)
    last_uid = store.get_last_uid(account, folder, uidvalidity)
    since_date = date.today() - timedelta(days=days)
    unseen_uids = client.get_unseen_uids(folder, since_date)

    if last_uid > 0:
        candidate_uids = [u for u in unseen_uids if u <= last_uid]
    else:
        candidate_uids = list(unseen_uids)

    candidate_uids = [
        u for u in candidate_uids if not store.is_seen(account, folder, uidvalidity, u, None)
    ]
    if not candidate_uids:
        return []

    raw_items = client.fetch_raw_batch(folder, candidate_uids)
    results: list[tuple[int, ParsedMail]] = []

    for uid, raw_bytes in raw_items:
        parsed = parse_raw(raw_bytes)
        if store.is_seen(account, folder, uidvalidity, uid, parsed.message_id):
            continue
        results.append((uid, parsed))

    return results


def commit_progress(
    store: Store,
    account: str,
    folder: str,
    uidvalidity: int,
    last_uid: int,
) -> None:
    """Zapisuje postęp przetwarzania folderu (last_uid)."""
    store.set_last_uid(account, folder, uidvalidity, last_uid)


def fetch_sent_message_ids(
    client: MailboxClient,
    sent_folder: str | None = None,
    days: int = 30,
) -> frozenset[str]:
    """Pobiera zbiór Message-ID z folderu wysłanych z ostatnich N dni.

    Wykorzystywane przez Rules.sent_message_ids.
    """
    candidates = get_sent_folder_candidates(sent_folder)
    working_folder: str | None = None
    for cand in candidates:
        try:
            client.get_uidvalidity(cand)
            working_folder = cand
            break
        except Exception:
            continue

    if not working_folder:
        checked = ", ".join(candidates[:4])
        raise FetchError(f"Nie odnaleziono folderu wiadomości wysłanych (sprawdzono: {checked})")

    since_date = date.today() - timedelta(days=days)
    raw_ids = client.get_sent_message_ids(working_folder, since_date)

    normalized: set[str] = set()
    for raw_id in raw_ids:
        norm = normalize_message_id(raw_id)
        if norm:
            normalized.add(norm)
    return frozenset(normalized)


class SentItemsList(list[tuple[int, ParsedMail]]):
    """Lista wiadomości wysłanych wraz z metadanymi folderu i uidvalidity."""

    def __init__(
        self,
        items: Sequence[tuple[int, ParsedMail]] = (),
        folder: str = "",
        uidvalidity: int = 0,
    ) -> None:
        super().__init__(items)
        self.folder = folder
        self.uidvalidity = uidvalidity


def fetch_sent_for_index(
    client: MailboxClient,
    store: Store,
    account: str,
    sent_folder: str | None = None,
    days: int = 30,
    limit: int = 100,
) -> SentItemsList:
    """Pobiera wysłane wiadomości z ostatnich N dni do zaindeksowania w mail_index.

    Wiadomości nie są oznaczane jako przeczytane (BODY.PEEK).
    Wiadomości już zaindeksowane w mail_index są pomijane.
    """
    candidates = get_sent_folder_candidates(sent_folder)
    working_folder: str | None = None
    uidvalidity: int = 0

    for cand in candidates:
        try:
            uidvalidity = client.get_uidvalidity(cand)
            working_folder = cand
            break
        except Exception:
            continue

    if not working_folder:
        raise FetchError(
            f"Nie odnaleziono folderu wiadomości wysłanych dla konta '{account}'. "
            f"Sprawdzono m.in.: {', '.join(candidates[:4])}"
        )

    since_date = date.today() - timedelta(days=days)
    uids = client.get_uids_since(working_folder, since_date)

    # Pomijamy UID, które już są w mail_index
    candidate_uids = [
        u for u in uids if not store.is_indexed(account, working_folder, uidvalidity, u)
    ]

    if not candidate_uids:
        return SentItemsList([], folder=working_folder, uidvalidity=uidvalidity)

    # Bierzemy najnowsze wiadomości do limitu
    if len(candidate_uids) > limit:
        candidate_uids = candidate_uids[-limit:]

    raw_items = client.fetch_raw_batch(working_folder, candidate_uids)
    results: list[tuple[int, ParsedMail]] = []

    for uid, raw_bytes in raw_items:
        parsed = parse_raw(raw_bytes)
        # Pomijamy jeśli message_id jest już w indeksie tego konta
        if store.is_indexed(account, working_folder, uidvalidity, uid, parsed.message_id):
            continue
        results.append((uid, parsed))

    return SentItemsList(results, folder=working_folder, uidvalidity=uidvalidity)
