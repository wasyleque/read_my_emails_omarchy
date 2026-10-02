"""Tłumaczenie technicznych błędów połączeń i logowania na czytelne komunikaty."""

import re
import socket
import ssl
from typing import Any


def format_friendly_error(exc: Any, lang: str = "pl") -> str:
    """Konwertuje techniczny wyjątek lub komunikat o błędzie na prosty język."""
    raw_str = str(exc).lower() if exc is not None else ""
    is_pl = lang.lower() == "pl"

    # 0. Model AI nie istnieje na serwerze Ollama (HTTP 404)
    if "http 404" in raw_str and ("model" in raw_str or "serwery ai" in raw_str):
        if is_pl:
            return (
                "Wybrany model AI nie jest zainstalowany na serwerze Ollama. "
                "Otwórz Ustawienia i wybierz model z listy zainstalowanych."
            )
        return (
            "The selected AI model is not installed on the Ollama server. "
            "Open Settings and pick a model from the installed list."
        )

    # 1. Specyficzne dla Gmaila hasło aplikacji / 2FA
    if (
        "application-specific password" in raw_str
        or "app-specific password" in raw_str
        or "web login required" in raw_str
        or "invalid credentials (failure)" in raw_str
        and "gmail" in raw_str
    ):
        if is_pl:
            return (
                "Gmail wymaga Hasła do aplikacji, a nie Twojego zwykłego hasła do konta Google. "
                "Możesz je wygenerować w ustawieniach konta Google w sekcji Bezpieczeństwo."
            )
        return (
            "Gmail requires an App Password rather than your standard account password. "
            "You can generate one under Google Account Security settings."
        )

    # 2. Złe hasło lub login
    if any(
        kw in raw_str
        for kw in (
            "authenticationfailed",
            "login failed",
            "invalid credentials",
            "bad credentials",
            "autherror",
            "brak hasła",
            "wrong password",
        )
    ):
        if is_pl:
            return "Hasło lub login nie pasują. Sprawdź, czy adres e-mail i hasło są poprawne."
        return "Incorrect username or password. Please verify your credentials."

    # 3. Błędy SSL/TLS
    if isinstance(exc, (ssl.SSLError, ssl.CertificateError)) or any(
        kw in raw_str
        for kw in (
            "ssl",
            "tls",
            "cert",
            "certificate verify failed",
            "wrong_version_number",
            "handshake",
            "insecure connection refused",
        )
    ):
        if is_pl:
            return (
                "Błąd bezpiecznego połączenia (SSL/TLS). Serwer pocztowy odrzucił szyfrowanie "
                "lub certyfikat jest nieprawidłowy."
            )
        return (
            "Secure connection error (SSL/TLS). The mail server rejected encryption "
            "or the certificate is invalid."
        )

    # 4. Błędy DNS (brak hosta)
    if isinstance(exc, socket.gaierror) or any(
        kw in raw_str for kw in ("name or service not known", "getaddrinfo failed", "nodename")
    ):
        if is_pl:
            return (
                "Nie odnaleziono serwera pocztowego o podanym adresie. "
                "Sprawdź, czy nazwa serwera (np. imap.example.com) została wpisana poprawnie."
            )
        return (
            "Mail server host not found. Please check the server address (e.g. imap.example.com)."
        )

    # 5. Brak połączenia / Timeout / Odmowa
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionRefusedError)) or any(
        kw in raw_str
        for kw in (
            "connection refused",
            "timed out",
            "network is unreachable",
            "connection reset",
            "host is down",
            "połączenie odrzucone",
            "brak serwera",
            "przekroczono czas oczekiwania",
            "nie można połączyć",
        )
    ):
        if is_pl:
            return (
                "Nie można połączyć się z serwerem. "
                "Sprawdź połączenie z internetem oraz numer portu (domyślnie 993)."
            )
        return (
            "Could not connect to the mail server. "
            "Check your internet connection and port number (default 993)."
        )

    # 6. Brak folderu (np. folderu Wysłane)
    if "folder" in raw_str and any(
        kw in raw_str
        for kw in (
            "wysłan",
            "sent",
            "nie odnaleziono",
            "not found",
            "does not exist",
            "brak folderu",
        )
    ):
        if is_pl:
            return (
                "Nie odnaleziono wskazanego folderu (np. folderu wiadomości wysłanych). "
                "Sprawdź konfigurację folderów w ustawieniach konta."
            )
        return (
            "The specified folder (e.g. sent messages folder) was not found. "
            "Please check folder configuration in account settings."
        )

    # Domyślny przyjazny komunikat dla nieznanych wyjątków
    if is_pl:
        return "Coś poszło nie tak. Spróbuj ponownie. Jeśli problem wraca, kliknij Szczegóły."
    return "Something went wrong. Please try again. If the problem persists, click Details."


def sanitize_error_details(exc: Any) -> str:
    """Tworzy bezpieczne podsumowanie techniczne błędu bez haseł i treści maili."""
    if exc is None:
        return "Brak szczegółów technicznych."

    exc_type = type(exc).__name__ if isinstance(exc, BaseException) else "Error"
    raw_desc = str(exc).strip()

    # Usunięcie haseł i tokenów z opisu technicznego
    clean_desc = re.sub(
        r"(?:password|hasło|haslo|secret|token|passwd|pwd)[\s:=]+[^\s,;]+",
        "[UKRYTE_HASŁO]",
        raw_desc,
        flags=re.IGNORECASE,
    )
    if len(clean_desc) > 300:
        clean_desc = clean_desc[:300] + "..."

    return f"Typ błędu: {exc_type}\nSzczegóły: {clean_desc}"


def format_friendly_error_ex(exc: Any, lang: str = "pl") -> tuple[str, str]:
    """Zwraca parę: (prosty komunikat dla użytkownika, bezpieczne szczegóły techniczne)."""
    friendly = format_friendly_error(exc, lang=lang)
    details = sanitize_error_details(exc)
    return friendly, details
