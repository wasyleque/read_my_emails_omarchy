"""Dobór modeli z listy zainstalowanych na serwerze Ollama (bez Qt, bez sieci).

Z listy wszystkich modeli wybiera te sensowne do oceny poczty, stawia zalecane na górze
i NIGDY nie proponuje modeli chmurowych (`:cloud`) — wysyłają dane poza Twój serwer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from mailvoice.core.analyzer import OllamaClient, build_messages, fetch_ollama_models
from mailvoice.core.config import OllamaConfig

# Fragmenty nazw, które wykluczają model z propozycji (nie nadają się do analizy poczty).
_EXCLUDED = (
    "cloud",  # płatne/zewnętrzne przekazanie danych do chmury Ollamy
    "embed",
    "nsfw",
    "uncensored",
    "abliterated",
    "heretic",
    "adult",
    "llava",
    "moondream",  # modele wizyjne
    "coder",
    "codegemma",
    "codeqwen",
    "codellama",
    "magicoder",
    "stable-code",
    "wizardcoder",
    "dolphincoder",  # modele do kodu
    "roominterior",
)

# Kolejność preferencji do ogólnej oceny (im wcześniej, tym lepiej).
_GENERAL_PREFERENCE = ("qwen3", "qwen2.5", "gemma3", "llama3.3", "llama3.1", "mistral", "llama3.2")


@dataclass(frozen=True)
class ModelChoice:
    general: str | None  # zalecany model ogólny
    polish: str | None  # zalecany model do polskiego (Bielik), jeśli jest
    choices: tuple[str, ...]  # lista do wyboru: zalecane na górze, bez wykluczonych


@dataclass(frozen=True)
class Detection:
    """Wynik wykrywania serwerów Ollama (lokalnego i LAN)."""

    models: list[str]
    source: str | None  # 'local' | 'lan' | None
    url: str | None
    local_ok: bool
    lan_ok: bool


@dataclass(frozen=True)
class CheckResult:
    """Wynik testowego zapytania do modelu Ollama."""

    ok: bool
    message: str
    elapsed_s: float = 0.0


def is_cloud_model(name: str) -> bool:
    low = name.lower()
    return ":cloud" in low or low.endswith("-cloud") or "-cloud:" in low


def _usable(name: str) -> bool:
    low = name.lower()
    return not any(bad in low for bad in _EXCLUDED)


def _rank(name: str) -> tuple[int, str]:
    low = name.lower()
    for i, prefix in enumerate(_GENERAL_PREFERENCE):
        if low.startswith(prefix) or f"/{prefix}" in low:
            return (i, low)
    return (len(_GENERAL_PREFERENCE), low)


def suggest_models(installed: list[str]) -> ModelChoice:
    usable = sorted((m for m in installed if _usable(m)), key=_rank)
    polish = next((m for m in usable if "bielik" in m.lower()), None)
    general = next((m for m in usable if "bielik" not in m.lower()), None) or polish
    return ModelChoice(general=general, polish=polish, choices=tuple(usable))


def get_available_models(installed: list[str], show_all: bool = False) -> list[str]:
    """Zwraca listę modeli do wyboru w interfejsie.

    Gdy show_all=False: tylko modele sensowne do oceny poczty (bez kodu, NSFW, wizyjnych itp.).
    Gdy show_all=True: wszystkie modele zainstalowane poza chmurowymi.
    Modele chmurowe (:cloud) są ZAWSZE wykluczone ze względów bezpieczeństwa i prywatności.
    """
    if not show_all:
        return list(suggest_models(installed).choices)
    non_cloud = [m for m in installed if not is_cloud_model(m)]
    return sorted(non_cloud, key=_rank)


def detect_models(
    local_url: str,
    lan_url: str,
    fetch: Callable[[str], list[str]] | None = None,
) -> Detection:
    """Odpytuje lokalny oraz sieciowy (LAN) serwer Ollama o listę modeli.

    Odpytuje oba endpointy, aby znać stan obu (local_ok, lan_ok),
    a listę modeli pobiera z pierwszego serwera, który odpowiedział.
    """
    fetch_fn = fetch or fetch_ollama_models

    local_models: list[str] = []
    local_ok = False
    if local_url:
        try:
            local_models = fetch_fn(local_url)
            local_ok = len(local_models) > 0
        except Exception:
            local_ok = False

    lan_models: list[str] = []
    lan_ok = False
    if lan_url:
        try:
            lan_models = fetch_fn(lan_url)
            lan_ok = len(lan_models) > 0
        except Exception:
            lan_ok = False

    if local_ok:
        return Detection(
            models=local_models,
            source="local",
            url=local_url,
            local_ok=True,
            lan_ok=lan_ok,
        )
    elif lan_ok:
        return Detection(
            models=lan_models,
            source="lan",
            url=lan_url,
            local_ok=False,
            lan_ok=True,
        )
    else:
        return Detection(
            models=[],
            source=None,
            url=None,
            local_ok=False,
            lan_ok=False,
        )


def describe_selection(saved_model: str | None, installed: list[str]) -> str:
    """Określa status wybranego modelu ('ok', 'missing', 'unknown')."""
    if not saved_model:
        return "unknown"
    if not installed:
        return "unknown"

    saved_clean = saved_model.strip().lower()
    installed_clean = {m.strip().lower() for m in installed}

    if saved_clean in installed_clean:
        return "ok"
    if ":" not in saved_clean and f"{saved_clean}:latest" in installed_clean:
        return "ok"
    if saved_clean.endswith(":latest") and saved_clean[:-7] in installed_clean:
        return "ok"
    if ":" not in saved_clean and any(m.split(":")[0] == saved_clean for m in installed_clean):
        return "ok"

    return "missing"


def check_model(
    cfg: OllamaConfig,
    model: str,
    client_factory: Callable[[OllamaConfig], OllamaClient] | None = None,
    lang: str = "pl",
) -> CheckResult:
    """Wysyła krótkie testowe zapytanie przez OllamaClient i weryfikuje poprawność modelu."""
    import time

    from mailvoice.core.friendly_errors import format_friendly_error

    test_cfg = OllamaConfig(
        lan_url=cfg.lan_url,
        local_url=cfg.local_url,
        model=model,
        polish_model=model,
        prefer=cfg.prefer,
        timeout_s=min(cfg.timeout_s, 15.0),
    )
    client = client_factory(test_cfg) if client_factory else OllamaClient(test_cfg)
    start_time = time.perf_counter()

    try:
        messages = build_messages(
            user_description="Weryfikacja sprawności modelu AI.",
            sender="mailvoice-check@local",
            subject="Test poprawności modelu",
            body="Wiadomość sprawdzająca łączność i poprawność schematu JSON z serwera Ollama.",
        )
        client.classify(messages, model=model)
        elapsed = time.perf_counter() - start_time
        msg = (
            f"Model działa poprawnie (czas odpowiedzi: {elapsed:.1f} s)"
            if lang == "pl"
            else f"Model is working correctly (response time: {elapsed:.1f} s)"
        )
        return CheckResult(ok=True, message=msg, elapsed_s=elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        friendly = format_friendly_error(exc, lang=lang)
        return CheckResult(ok=False, message=friendly, elapsed_s=elapsed)
