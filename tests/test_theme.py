"""Kontrast kolorów w obu motywach oraz zakaz kolorów wpisanych na sztywno w widżetach."""

import re
from pathlib import Path

import pytest

from mailvoice.ui import theme

UI = Path(__file__).resolve().parents[1] / "src/mailvoice/ui"


def _lum(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# tło, na którym dana rola jest używana, w każdym motywie
WINDOW = {False: "#f6f5f4", True: "#242424"}  # typowe tła okna: jasny / ciemny (Adwaita/Omarchy)


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("role", ["muted", "accent", "link", "ok", "warn", "error"])
def test_text_roles_readable_on_window_and_cards(role, dark):
    fg = theme.c(role, dark=dark)
    assert _contrast(fg, WINDOW[dark]) >= 4.5, f"{role} nieczytelny na tle okna ({dark=})"
    assert _contrast(fg, theme.c("card_bg", dark=dark)) >= 4.5, f"{role} nieczytelny na karcie"


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("key", ["high", "medium", "low"])
def test_badges_readable(key, dark):
    bg, fg = theme.c(f"badge_{key}_bg", dark=dark), theme.c(f"badge_{key}_fg", dark=dark)
    assert _contrast(fg, bg) >= 4.5


def test_no_hardcoded_colors_in_widgets():
    """Regresja: ciemnoszary tekst na ciemnym tle. Kolory tylko przez theme.c()."""
    bad = []
    for path in UI.glob("*.py"):
        if path.name in ("theme.py", "i18n.py"):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{3,6}\b", line) or re.search(
                r"color:\s*(red|green|blue|black|white|gray|grey)\b", line
            ):
                bad.append(f"{path.name}:{n}")
    assert not bad, "kolory wpisane na sztywno: " + ", ".join(bad)
