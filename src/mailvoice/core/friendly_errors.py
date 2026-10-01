"""Tłumaczenie technicznych błędów połączeń i logowania na czytelne komunikaty."""

import socket
import ssl
from typing import Any


def format_friendly_error(exc: Any, lang: str = "pl") -> str:
    """Konwertuje techniczny wyjątek lub komunikat o błędzie na prosty język."""
    raw_str = str(exc).lower() if exc is not None else ""
    is_pl = lang.lower() == "pl"

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
            "Mail server host not found. "
            "Please check the server address (e.g. imap.example.com)."
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

    # Domyślny przyjazny komunikat
    clean_msg = str(exc).strip()
    if is_pl:
        return f"Wystąpił nieoczekiwany problem z połączeniem: {clean_msg}"
    return f"An unexpected connection issue occurred: {clean_msg}"
