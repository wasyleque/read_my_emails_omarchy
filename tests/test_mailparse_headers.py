"""Testy parsowania nagłówków To i Cc oraz zgodności wstecznej ParsedMail."""

from datetime import datetime, timezone

from mailvoice.core.mailparse import ParsedMail, parse_raw


def test_parsed_mail_backward_compatibility():
    """Weryfikuje, że ParsedMail można tworzyć bez podawania to i cc."""
    mail = ParsedMail(
        message_id="<123@test>",
        sender="anna@firma.pl",
        subject="Spotkanie",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="Cześć",
    )
    assert mail.to == ()
    assert mail.cc == ()


def test_parse_raw_extracts_to_and_cc():
    raw_email = (
        b"From: Szef <szef@firma.pl>\r\n"
        b"To: Jan Kowalski <jan@firma.pl>, Piotr <piotr@firma.pl>\r\n"
        b"Cc: Dyrektor <dyrektor@firma.pl>, Jan <jan@firma.pl>\r\n"
        b"Subject: Pilny projekt\r\n"
        b"Message-ID: <msg99@firma.pl>\r\n"
        b"\r\n"
        b"Wiadomosc testowa..."
    )

    parsed = parse_raw(raw_email)
    assert parsed.sender == "Szef <szef@firma.pl>"
    assert parsed.to == ("jan@firma.pl", "piotr@firma.pl")
    # jan@firma.pl w cc nie powiela się jeśli jest już znormalizowany
    assert "dyrektor@firma.pl" in parsed.cc
