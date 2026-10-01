from datetime import datetime, timezone
from email.message import EmailMessage

from mailvoice.core.mailparse import parse_raw


def create_email_message(**kwargs):
    """Helper to create an email message with given headers and body"""
    msg = EmailMessage()

    # Set headers
    for key, value in kwargs.items():
        if key == "body":
            msg.set_content(value)
        else:
            msg[key.replace("_", "-")] = value

    return msg


def test_plain_text_email():
    """Test parsing a plain text email"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="Test Subject",
        Date="Mon, 01 Jan 2023 12:00:00 +0000",
        Message_ID="<test123@example.com>",
        In_Reply_To="<reply123@example.com>",
        References="<ref1@example.com> <ref2@example.com>",
        body="This is a plain text email body.",
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.message_id == "<test123@example.com>"
    assert parsed.sender == "sender@example.com"
    assert parsed.subject == "Test Subject"
    assert parsed.date == datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert parsed.in_reply_to == "<reply123@example.com>"
    assert parsed.references == ("<ref1@example.com>", "<ref2@example.com>")
    assert parsed.body_text == "This is a plain text email body."


def test_html_email():
    """Test parsing an HTML email"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="HTML Test",
        Date="Mon, 01 Jan 2023 12:00:00 +0000",
    )
    msg.set_content("<p>This is <b>HTML</b> content.</p>", subtype="html")

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.sender == "sender@example.com"
    assert parsed.subject == "HTML Test"
    assert parsed.date == datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert parsed.body_text == "This is HTML content."


def test_multipart_alternative():
    """Test parsing multipart/alternative email (should prefer plain)"""
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["Subject"] = "Multipart Test"
    msg["Date"] = "Mon, 01 Jan 2023 12:00:00 +0000"

    # Create multipart message
    msg.set_content("This is plain text", subtype="plain")
    msg.add_alternative("<p>This is HTML</p>", subtype="html")

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.body_text == "This is plain text"


def test_polish_subject():
    """Test parsing email with Polish characters in subject"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="=?utf-8?b?xZpjacSFZ25paiBwbGlr?=",
        body="Body content",
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.subject == "Ściągnij plik"


def test_references_with_multiple_ids():
    """Test parsing email with multiple references"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="Test",
        References="<ref1@example.com> <ref2@example.com> <ref3@example.com>",
        body="Body content",
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.references == ("<ref1@example.com>", "<ref2@example.com>", "<ref3@example.com>")


def test_missing_headers():
    """Test parsing email with missing headers"""
    msg = create_email_message(body="Body content")

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.message_id is None
    assert parsed.sender == ""
    assert parsed.subject == ""
    assert parsed.date is None
    assert parsed.in_reply_to is None
    assert parsed.references == ()
    assert parsed.body_text == "Body content"


def test_broken_date():
    """Test parsing email with broken date"""
    msg = create_email_message(
        From="sender@example.com", Subject="Test", Date="Invalid Date Format", body="Body content"
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.date is None


def test_email_with_citation():
    """Test parsing email with citation (should be cleaned by clean_body)"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="Test",
        body="> This is a quote\n\nThis is the main content.",
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    # The citation should be removed by clean_body
    assert "quote" not in parsed.body_text.lower()


def test_empty_email():
    """Test parsing empty email"""
    msg = EmailMessage()
    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.message_id is None
    assert parsed.sender == ""
    assert parsed.subject == ""
    assert parsed.date is None
    assert parsed.in_reply_to is None
    assert parsed.references == ()
    assert parsed.body_text == ""


def test_message_id_without_angle_brackets():
    """Test parsing message ID without angle brackets"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="Test",
        Message_ID="test123@example.com",
        body="Body content",
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.message_id == "test123@example.com"


def test_message_id_with_angle_brackets():
    """Test parsing message ID with angle brackets"""
    msg = create_email_message(
        From="sender@example.com",
        Subject="Test",
        Message_ID="<test123@example.com>",
        body="Body content",
    )

    raw = msg.as_bytes()
    parsed = parse_raw(raw)

    assert parsed.message_id == "<test123@example.com>"
