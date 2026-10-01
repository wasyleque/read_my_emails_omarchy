import email
import email.policy
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

from mailvoice.core.textutil import clean_body, html_to_text


@dataclass(frozen=True)
class ParsedMail:
    message_id: str | None
    sender: str
    subject: str
    date: datetime | None
    in_reply_to: str | None
    references: tuple[str, ...]
    body_text: str


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

    return ParsedMail(
        message_id=message_id,
        sender=sender,
        subject=subject,
        date=date,
        in_reply_to=in_reply_to,
        references=references,
        body_text=body_text,
    )
