"""Predefiniowane szablony dostawców poczty IMAP."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    """Informacje konfiguracyjne dla znanego dostawcy poczty."""

    provider_id: str
    display_name: str
    host: str
    port: int = 993
    use_ssl: bool = True
    sent_folder: str = "Sent"
    help_text_pl: str = ""
    help_text_en: str = ""


PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        provider_id="gmail",
        display_name="Gmail (Google)",
        host="imap.gmail.com",
        port=993,
        use_ssl=True,
        sent_folder="[Gmail]/Sent Mail",
        help_text_pl=(
            "Gmail wymaga Hasła do aplikacji. Wejdź na myaccount.google.com -> "
            "Bezpieczeństwo -> Weryfikacja dwuetapowa -> Hasła do aplikacji i wygeneruj nowe."
        ),
        help_text_en=(
            "Gmail requires an App Password. Visit myaccount.google.com -> "
            "Security -> 2-Step Verification -> App Passwords to create one."
        ),
    ),
    ProviderInfo(
        provider_id="outlook",
        display_name="Outlook / Microsoft 365",
        host="outlook.office365.com",
        port=993,
        use_ssl=True,
        sent_folder="Sent Items",
        help_text_pl=(
            "Dla kont osobistych (@outlook.com, @hotmail.com) lub firmowych Microsoft 365. "
            "W przypadku weryfikacji dwuetapowej wymagane jest hasło aplikacji."
        ),
        help_text_en=(
            "For personal (@outlook.com, @hotmail.com) or Microsoft 365 accounts. "
            "If two-step verification is enabled, use an app password."
        ),
    ),
    ProviderInfo(
        provider_id="wp",
        display_name="Wirtualna Polska (WP.pl)",
        host="poczta.wp.pl",
        port=993,
        use_ssl=True,
        sent_folder="Wysłane",
        help_text_pl="Upewnij się, że w opcjach poczty WP włączona jest obsługa protokołu IMAP.",
        help_text_en="Ensure IMAP access is enabled in WP Mail settings.",
    ),
    ProviderInfo(
        provider_id="onet",
        display_name="Onet Poczta",
        host="poczta.onet.pl",
        port=993,
        use_ssl=True,
        sent_folder="Wysłane",
        help_text_pl="Włącz dostęp IMAP w ustawieniach konta Onet Poczta.",
        help_text_en="Enable IMAP access in Onet Mail settings.",
    ),
    ProviderInfo(
        provider_id="o2",
        display_name="O2 Poczta",
        host="poczta.o2.pl",
        port=993,
        use_ssl=True,
        sent_folder="Wysłane",
        help_text_pl="Upewnij się, że protokół IMAP jest włączony w ustawieniach poczty O2.",
        help_text_en="Ensure IMAP protocol is enabled in O2 settings.",
    ),
    ProviderInfo(
        provider_id="interia",
        display_name="Interia Poczta",
        host="poczta.interia.pl",
        port=993,
        use_ssl=True,
        sent_folder="Wysłane",
        help_text_pl="Upewnij się, że w opcjach konta włączona jest obsługa IMAP.",
        help_text_en="Ensure IMAP access is enabled in Interia settings.",
    ),
    ProviderInfo(
        provider_id="other",
        display_name="Inny serwer (własny IMAP)",
        host="",
        port=993,
        use_ssl=True,
        sent_folder="Sent",
        help_text_pl="Wprowadź adres i port swojego serwera pocztowego IMAP.",
        help_text_en="Enter your custom IMAP mail server address and port.",
    ),
]


def get_providers() -> list[ProviderInfo]:
    """Zwraca listę wszystkich obsługiwanych szablonów dostawców."""
    return list(PROVIDERS)


def get_provider_by_id(provider_id: str) -> ProviderInfo:
    """Zwraca szablon dostawcy po identyfikatorze lub 'other' jeśli nie znaleziono."""
    for p in PROVIDERS:
        if p.provider_id == provider_id:
            return p
    return PROVIDERS[-1]  # 'other'


COMMON_SENT_FOLDERS: tuple[str, ...] = (
    "Sent",
    "Sent Items",
    "Sent Messages",
    "[Gmail]/Sent Mail",
    "[Gmail]/Wysłane",
    "Wysłane",
    "Elementy wysłane",
    "INBOX.Sent",
    "INBOX.Wysłane",
    "INBOX/Sent",
)


def get_sent_folder_candidates(configured: str | None = None) -> list[str]:
    """Zwraca uporządkowaną listę potencjalnych nazw folderu wysłanych dla różnych dostawców."""
    candidates: list[str] = []
    if configured and configured.strip():
        candidates.append(configured.strip())

    for folder in COMMON_SENT_FOLDERS:
        if folder not in candidates:
            candidates.append(folder)

    return candidates
