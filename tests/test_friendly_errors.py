"""Testy mapowania błędów technicznych na komunikaty w prostym języku."""

import socket
import ssl

from mailvoice.core.friendly_errors import format_friendly_error


def test_gmail_app_password_error():
    err_msg = (
        "[AUTHENTICATIONFAILED] Application-specific password required: https://support.google.com"
    )
    msg_pl = format_friendly_error(err_msg, lang="pl")
    assert "Hasła do aplikacji" in msg_pl
    assert "myaccount.google.com" in msg_pl or "ustawieniach konta Google" in msg_pl

    msg_en = format_friendly_error(err_msg, lang="en")
    assert "App Password" in msg_en


def test_bad_credentials_error():
    err_msg = "IMAP4 login failed: [AUTHENTICATIONFAILED] Invalid credentials"
    msg_pl = format_friendly_error(err_msg, lang="pl")
    assert "Hasło lub login nie pasują" in msg_pl

    msg_en = format_friendly_error(err_msg, lang="en")
    assert "Incorrect username or password" in msg_en


def test_dns_host_not_found():
    exc = socket.gaierror(-2, "Name or service not known")
    msg_pl = format_friendly_error(exc, lang="pl")
    assert "Nie odnaleziono serwera" in msg_pl

    msg_en = format_friendly_error(exc, lang="en")
    assert "host not found" in msg_en


def test_ssl_error():
    exc = ssl.SSLError("certificate verify failed")
    msg_pl = format_friendly_error(exc, lang="pl")
    assert "SSL/TLS" in msg_pl
    assert "bezpiecznego połączenia" in msg_pl


def test_timeout_error():
    exc = TimeoutError("Connection timed out")
    msg_pl = format_friendly_error(exc, lang="pl")
    assert "Nie można połączyć się z serwerem" in msg_pl
    assert "połączenie z internetem" in msg_pl


def test_unknown_error_shows_friendly_message_without_raw_trace():
    exc = AttributeError("'ImapToolsClient' object has no attribute 'login'")
    msg_pl = format_friendly_error(exc, lang="pl")
    assert "Coś poszło nie tak" in msg_pl
    assert "kliknij Szczegóły" in msg_pl
    assert "AttributeError" not in msg_pl
    assert "ImapToolsClient" not in msg_pl

    msg_en = format_friendly_error(exc, lang="en")
    assert "Something went wrong" in msg_en
    assert "click Details" in msg_en
    assert "AttributeError" not in msg_en


def test_sanitize_error_details_masks_passwords_and_tokens():
    from mailvoice.core.friendly_errors import format_friendly_error_ex, sanitize_error_details

    exc = ValueError("Failed connection with password=SuperSecretPass123 and token=XYZ98765")
    details = sanitize_error_details(exc)
    assert "Typ błędu: ValueError" in details
    assert "SuperSecretPass123" not in details
    assert "XYZ98765" not in details
    assert "[UKRYTE_HASŁO]" in details

    # Sprawdzenie format_friendly_error_ex
    friendly, details_ex = format_friendly_error_ex(exc, lang="pl")
    assert "Coś poszło nie tak" in friendly
    assert details_ex == details
