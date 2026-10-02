"""Dobór modeli z listy zainstalowanych na serwerze Ollama (bez Qt, bez sieci).

Z listy wszystkich modeli wybiera te sensowne do oceny poczty, stawia zalecane na górze
i NIGDY nie proponuje modeli chmurowych (`:cloud`) — wysyłają dane poza Twój serwer.
"""

from __future__ import annotations

from dataclasses import dataclass

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
