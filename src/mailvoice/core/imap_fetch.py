import base64
import quopri
from datetime import date, timedelta
from typing import Any, Protocol, Sequence

from imap_tools import A, MailBox

from mailvoice.core.mailparse import AttachmentInfo, ParsedMail, parse_raw
from mailvoice.core.providers import get_sent_folder_candidates
from mailvoice.core.store import Store
from mailvoice.core.textutil import clean_body, html_to_text


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

    def fetch_raw_batch(
        self, folder: str, uids: Sequence[int]
    ) -> list[tuple[int, ParsedMail | bytes]]:
        """Pobiera bezpieczną reprezentację wiadomości (bez treści załączników)."""
        ...

    def fetch_message_body(self, folder: str, uid: int) -> str | None:
        """Pobiera bezpieczną treść tekstową pojedynczej wiadomości (BODY.PEEK)."""
        ...

    def get_sent_message_ids(self, folder: str, since_date: date) -> list[str]:
        """Pobiera nagłówki Message-ID wiadomości wysłanych od podanej daty."""
        ...

    def close(self) -> None:
        """Zamyka połączenie ze skrzynką pocztową."""
        ...


def _parse_s_expression(s: str) -> list[Any] | str:
    """Parsuje wyrażenie nawiasowe IMAP (s-expression) do zagnieżdżonej listy Pythona."""
    tokens: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            i += 1
            chars: list[str] = []
            while i < n:
                if s[i] == "\\" and i + 1 < n:
                    chars.append(s[i + 1])
                    i += 2
                elif s[i] == '"':
                    break
                else:
                    chars.append(s[i])
                    i += 1
            tokens.append("".join(chars))
            if i < n and s[i] == '"':
                i += 1
        else:
            start = i
            while i < n and not s[i].isspace() and s[i] not in "()":
                i += 1
            tokens.append(s[start:i])

    def _build_tree(toks: list[str], idx: int) -> tuple[Any, int]:
        if idx >= len(toks):
            return [], idx
        if toks[idx] == "(":
            res: list[Any] = []
            idx += 1
            while idx < len(toks) and toks[idx] != ")":
                item, idx = _build_tree(toks, idx)
                res.append(item)
            if idx < len(toks) and toks[idx] == ")":
                idx += 1
            return res, idx
        else:
            val = toks[idx]
            if val.upper() == "NIL":
                return None, idx + 1
            return val, idx + 1

    tree, _ = _build_tree(tokens, 0)
    return tree if isinstance(tree, list) else [tree]


def _extract_mime_parts(
    struct: Any, prefix: str = ""
) -> tuple[list[tuple[str, str, str, str]], list[AttachmentInfo]]:
    """Wyciąga części tekstowe oraz metadane załączników z drzewa BODYSTRUCTURE.

    Zwraca:
      text_parts: [(part_id, subtype, encoding, charset), ...]
      attachments: [AttachmentInfo, ...]
    """
    text_parts: list[tuple[str, str, str, str]] = []
    attachments: list[AttachmentInfo] = []

    if not isinstance(struct, list) or not struct:
        return text_parts, attachments

    if isinstance(struct[0], list):
        part_idx = 1
        for item in struct:
            if isinstance(item, list):
                sub_prefix = f"{prefix}.{part_idx}" if prefix else str(part_idx)
                sub_texts, sub_att = _extract_mime_parts(item, prefix=sub_prefix)
                text_parts.extend(sub_texts)
                attachments.extend(sub_att)
                part_idx += 1
            else:
                break
        return text_parts, attachments

    main_type = str(struct[0]).upper() if len(struct) > 0 and struct[0] else ""
    sub_type = str(struct[1]).upper() if len(struct) > 1 and struct[1] else ""
    body_params = struct[2] if len(struct) > 2 and isinstance(struct[2], list) else []
    encoding = str(struct[5]).upper() if len(struct) > 5 and struct[5] else ""

    size = 0
    if len(struct) > 6 and struct[6] is not None:
        try:
            size = int(struct[6])
        except (ValueError, TypeError):
            size = 0

    filename = ""
    disposition_type = ""
    for elem in struct[7:]:
        if isinstance(elem, list) and len(elem) >= 1 and isinstance(elem[0], str):
            disp = elem[0].upper()
            if disp in ("ATTACHMENT", "INLINE"):
                disposition_type = disp
                if len(elem) > 1 and isinstance(elem[1], list):
                    disp_params = elem[1]
                    for k in range(0, len(disp_params) - 1, 2):
                        if str(disp_params[k]).upper() == "FILENAME":
                            filename = str(disp_params[k + 1])
                            break
                break

    if not filename and body_params:
        for k in range(0, len(body_params) - 1, 2):
            if str(body_params[k]).upper() == "NAME":
                filename = str(body_params[k + 1])
                break

    charset = "utf-8"
    if body_params:
        for k in range(0, len(body_params) - 1, 2):
            if str(body_params[k]).upper() == "CHARSET":
                charset = str(body_params[k + 1]).lower()
                break

    content_type = (
        f"{main_type.lower()}/{sub_type.lower()}"
        if main_type and sub_type
        else "application/octet-stream"
    )

    is_attachment = (
        disposition_type == "ATTACHMENT"
        or (disposition_type == "INLINE" and filename)
        or bool(filename)
        or (main_type and main_type != "TEXT")
    )

    if is_attachment:
        att_name = filename or f"part_{prefix or '1'}"
        attachments.append(AttachmentInfo(name=att_name, content_type=content_type, size=size))
    elif main_type == "TEXT":
        part_id = prefix if prefix else "TEXT"
        text_parts.append((part_id, sub_type, encoding, charset))

    return text_parts, attachments


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

    def _fetch_safe_mail(self, mailbox: MailBox, uid: int) -> ParsedMail | None:
        """Pobiera nagłówki i części tekstowe bez pobierania zawartości załączników."""
        try:
            typ, data = mailbox.client.uid("FETCH", str(uid), "(BODYSTRUCTURE BODY.PEEK[HEADER])")
            if typ != "OK" or not data or not data[0]:
                return self._fetch_headers_only_safe(mailbox, uid)

            header_bytes = b""
            bodystructure_str = ""

            for item in data:
                if isinstance(item, tuple) and len(item) >= 2:
                    header_bytes = item[1]
                    info_line = item[0].decode("latin1", errors="replace")
                    bs_idx = info_line.find("BODYSTRUCTURE")
                    if bs_idx != -1:
                        bodystructure_str = info_line[bs_idx + len("BODYSTRUCTURE") :].strip()
                elif isinstance(item, bytes):
                    item_str = item.decode("latin1", errors="replace")
                    bs_idx = item_str.find("BODYSTRUCTURE")
                    if bs_idx != -1 and not bodystructure_str:
                        bodystructure_str = item_str[bs_idx + len("BODYSTRUCTURE") :].strip()

            parsed_headers = parse_raw(header_bytes)
            if not bodystructure_str:
                return parsed_headers

            struct = _parse_s_expression(bodystructure_str)
            text_parts, attachments = _extract_mime_parts(struct)

            body_text = ""
            chosen_part = None
            for p in text_parts:
                if p[1] == "PLAIN":
                    chosen_part = p
                    break
            if not chosen_part and text_parts:
                chosen_part = text_parts[0]

            if chosen_part:
                part_id, sub_type, encoding, charset = chosen_part
                part_query = f"BODY.PEEK[{part_id}]<0.262144>"
                typ_p, data_p = mailbox.client.uid("FETCH", str(uid), f"({part_query})")
                if typ_p == "OK" and data_p and isinstance(data_p[0], tuple):
                    part_bytes = data_p[0][1]
                    if encoding == "BASE64":
                        try:
                            part_bytes = base64.b64decode(part_bytes)
                        except Exception:
                            pass
                    elif encoding == "QUOTED-PRINTABLE":
                        part_bytes = quopri.decodestring(part_bytes)

                    try:
                        text_content = part_bytes.decode(charset, errors="replace")
                    except Exception:
                        text_content = part_bytes.decode("utf-8", errors="replace")

                    if sub_type == "HTML":
                        text_content = html_to_text(text_content)
                    body_text = clean_body(text_content)

            return ParsedMail(
                message_id=parsed_headers.message_id,
                sender=parsed_headers.sender,
                subject=parsed_headers.subject,
                date=parsed_headers.date,
                in_reply_to=parsed_headers.in_reply_to,
                references=parsed_headers.references,
                body_text=body_text or parsed_headers.body_text,
                to=parsed_headers.to,
                cc=parsed_headers.cc,
                attachments=tuple(attachments) or parsed_headers.attachments,
                reply_to=parsed_headers.reply_to,
                authentication_results=parsed_headers.authentication_results,
                return_path=parsed_headers.return_path,
                links=parsed_headers.links,
            )
        except Exception:
            return self._fetch_headers_only_safe(mailbox, uid)

    def _fetch_headers_only_safe(self, mailbox: MailBox, uid: int) -> ParsedMail | None:
        """Bezpieczny fallback: pobiera wyłącznie nagłówki wiadomości bez załączników."""
        try:
            typ, data = mailbox.client.uid("FETCH", str(uid), "(BODY.PEEK[HEADER])")
            if typ != "OK" or not data:
                return None
            header_bytes = b""
            for item in data:
                if isinstance(item, tuple) and len(item) >= 2:
                    header_bytes = item[1]
                    break
            if not header_bytes:
                return None
            h_mail = parse_raw(header_bytes)
            return ParsedMail(
                message_id=h_mail.message_id,
                sender=h_mail.sender,
                subject=h_mail.subject,
                date=h_mail.date,
                in_reply_to=h_mail.in_reply_to,
                references=h_mail.references,
                body_text="[Treść niedostępna — bezpieczny tryb]",
                to=h_mail.to,
                cc=h_mail.cc,
                attachments=(),
                reply_to=h_mail.reply_to,
                authentication_results=h_mail.authentication_results,
                return_path=h_mail.return_path,
                links=(),
            )
        except Exception:
            return None

    def fetch_raw_batch(self, folder: str, uids: Sequence[int]) -> list[tuple[int, ParsedMail]]:
        if not uids:
            return []
        mailbox = self._get_mailbox()
        try:
            mailbox.folder.set(folder)
            results: list[tuple[int, ParsedMail]] = []
            for uid in uids:
                parsed = self._fetch_safe_mail(mailbox, uid)
                if parsed:
                    results.append((uid, parsed))
            return results
        except FetchError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_message(str(exc))
            raise FetchError(
                f"Błąd pobierania wiadomości z folderu '{folder}': {sanitized}"
            ) from None

    def fetch_message_body(self, folder: str, uid: int) -> str | None:
        """Pobiera bezpieczną treść tekstową pojedynczej wiadomości (BODY.PEEK)."""
        items = self.fetch_raw_batch(folder, [uid])
        if not items:
            return None
        _, mail = items[0]
        if isinstance(mail, ParsedMail):
            return mail.body_text
        return None

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

    for uid, item in raw_items:
        parsed = item if isinstance(item, ParsedMail) else parse_raw(item)
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

    for uid, item in raw_items:
        parsed = item if isinstance(item, ParsedMail) else parse_raw(item)
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

    for uid, item in raw_items:
        parsed = item if isinstance(item, ParsedMail) else parse_raw(item)
        # Pomijamy jeśli message_id jest już w indeksie tego konta
        if store.is_indexed(account, working_folder, uidvalidity, uid, parsed.message_id):
            continue
        results.append((uid, parsed))

    return SentItemsList(results, folder=working_folder, uidvalidity=uidvalidity)
