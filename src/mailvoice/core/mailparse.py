import email
import email.policy
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import getaddresses, parsedate_to_datetime

from mailvoice.core.textutil import clean_body, html_to_text


@dataclass(frozen=True)
class AttachmentInfo:
    """Metadane załącznika (nazwa, typ, rozmiar w bajtach; treść nie jest pobierana)."""

    name: str
    content_type: str
    size: int


@dataclass(frozen=True)
class ParsedMail:
    message_id: str | None
    sender: str
    subject: str
    date: datetime | None
    in_reply_to: str | None
    references: tuple[str, ...]
    body_text: str
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    attachments: tuple[AttachmentInfo, ...] = ()
    reply_to: str | None = None
    authentication_results: str | None = None
    return_path: str | None = None
    links: tuple[str, ...] = ()


def parse_raw(raw: bytes) -> ParsedMail:
    # Parse the raw email message
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    message_id = str(msg.get("Message-ID", "")).strip() or None
    sender = str(msg.get("From", "")).strip()
    subject = str(msg.get("Subject", "")).strip()

    # Extract date
    date_str = msg.get("Date")
    date = None
    if date_str:
        try:
            date = parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            pass  # Keep date as None if parsing fails

    # Extract in_reply_to
    in_reply_to = str(msg.get("In-Reply-To", "")).strip() or None

    # Extract references
    references = msg.get("References", "")
    if references:
        references = tuple(ref.strip() for ref in references.split())
    else:
        references = ()

    # Extract body text
    body_text = ""
    body_part = msg.get_body(preferencelist=("plain", "html"))

    if body_part:
        content = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            content = html_to_text(content)
        body_text = clean_body(content)

    # Extract recipients (To and Cc)
    def _extract_addrs(header_name: str) -> tuple[str, ...]:
        header_vals = msg.get_all(header_name, [])
        if not header_vals:
            return ()
        raw_tuples = getaddresses(header_vals)
        res: list[str] = []
        for _name, addr in raw_tuples:
            clean = addr.strip().lower()
            if clean and clean not in res:
                res.append(clean)
        return tuple(res)

    to_addrs = _extract_addrs("to")
    cc_addrs = _extract_addrs("cc")

    reply_to = str(msg.get("Reply-To", "")).strip() or None
    authentication_results = str(msg.get("Authentication-Results", "")).strip() or None
    return_path = str(msg.get("Return-Path", "")).strip() or None

    # Wykrywanie załączników (tylko metadane, bez przechowywania treści)
    attachments_list: list[AttachmentInfo] = []
    ignored_types = {
        "text/plain",
        "text/html",
        "multipart/mixed",
        "multipart/alternative",
        "multipart/related",
        "multipart/signed",
    }
    for part in msg.walk():
        cd = str(part.get("Content-Disposition", ""))
        fn = part.get_filename()
        ct = part.get_content_type()
        is_att = (
            "attachment" in cd.lower()
            or bool(fn)
            or (ct not in ignored_types and "inline" not in cd.lower())
        )
        if is_att:
            name = fn or "unnamed"
            payload = part.get_payload()
            size = len(payload) if isinstance(payload, (bytes, str)) else 0
            attachments_list.append(AttachmentInfo(name=name, content_type=ct, size=size))

    # Wyciąganie linków z części HTML oraz tekstu (bez ich odwiedzania)
    url_re = re.compile(r"https?://[^\s<>\"')]+|www\.[^\s<>\"')]+", re.IGNORECASE)
    href_re = re.compile(r'href=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
    extracted_links: list[str] = []

    has_html = False
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/html":
            has_html = True
            try:
                html_c = part.get_content()
                for href in href_re.findall(html_c):
                    clean_h = href.strip()
                    if clean_h and clean_h not in extracted_links:
                        extracted_links.append(clean_h)
            except Exception:
                pass
        elif ct == "text/plain":
            try:
                plain_c = part.get_content()
                for u in url_re.findall(plain_c):
                    clean_u = u.strip()
                    if clean_u and clean_u not in extracted_links:
                        extracted_links.append(clean_u)
            except Exception:
                pass

    if not has_html and body_text:
        for u in url_re.findall(body_text):
            clean_u = u.strip()
            if clean_u and clean_u not in extracted_links:
                extracted_links.append(clean_u)

    return ParsedMail(
        message_id=message_id,
        sender=sender,
        subject=subject,
        date=date,
        in_reply_to=in_reply_to,
        references=references,
        body_text=body_text,
        to=to_addrs,
        cc=cc_addrs,
        attachments=tuple(attachments_list),
        reply_to=reply_to,
        authentication_results=authentication_results,
        return_path=return_path,
        links=tuple(extracted_links),
    )
