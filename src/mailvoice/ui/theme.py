"""Kolory interfejsu dobierane do motywu (jasny/ciemny) — czytelny kontrast w obu trybach.

Nie wpisujemy kolorów na sztywno w widżetach: używamy `theme.c("rola")`.
Wszystkie role mają kontrast co najmniej 4,5:1 względem tła swojego motywu (test w tests/).
"""

from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

# rola -> (jasny motyw, ciemny motyw)
_ROLES: dict[str, tuple[str, str]] = {
    "muted": ("#4d5560", "#b9c1cb"),  # tekst pomocniczy
    "accent": ("#1a5fb4", "#8cb8f0"),
    "link": ("#0b5ed7", "#8cb8f0"),
    "ok": ("#18742f", "#72d68b"),
    "warn": ("#9a4e00", "#ffb454"),
    "error": ("#b02a37", "#ff8a80"),
    "card_bg": ("#f6f8fa", "#2b3038"),
    "card_border": ("#c9d1d9", "#555d68"),
    "mute_bg": ("#ffd8a8", "#6b4a14"),
    "guide_bg": ("#eef1f4", "#2f353d"),
    # odznaki pewności: tło, tekst
    "badge_high_bg": ("#d1e7dd", "#1f4d36"),
    "badge_high_fg": ("#0f5132", "#b6f0cf"),
    "badge_medium_bg": ("#fff3cd", "#5c4a12"),
    "badge_medium_fg": ("#664d03", "#ffe69c"),
    "badge_low_bg": ("#e2e3e5", "#40454c"),
    "badge_low_fg": ("#41464b", "#d3d7dc"),
}


def is_dark() -> bool:
    app = QApplication.instance()
    palette = app.palette() if app is not None else QPalette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def c(role: str, dark: bool | None = None) -> str:
    """Kolor roli dla bieżącego motywu. Rola `text` = kolor tekstu z palety systemowej."""
    if dark is None:
        dark = is_dark()
    if role == "text":
        app = QApplication.instance()
        palette = app.palette() if app is not None else QPalette()
        return palette.color(QPalette.ColorRole.WindowText).name()
    light_value, dark_value = _ROLES[role]
    return dark_value if dark else light_value


def badge(confidence: str) -> tuple[str, str]:
    """(tło, tekst) odznaki pewności: wysoka / średnia / niska."""
    key = {"wysoka": "high", "średnia": "medium"}.get(confidence, "low")
    return c(f"badge_{key}_bg"), c(f"badge_{key}_fg")


def roles() -> tuple[str, ...]:
    return tuple(_ROLES)
