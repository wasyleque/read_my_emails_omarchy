"""Testy okna IgnoreDialog („Ignoruj" / „VIP").

Regresja: przy starcie `setChecked(True)` emitowało `toggled`, które wywoływało
`_update_preview` zanim powstał `self._preview` → AttributeError trafiający do excepthooka
(użytkownik widział „Coś poszło nie tak", choć reguła i tak się dodawała). PySide6 nie
przepuszcza wyjątku ze slota, więc łapiemy go przez podmianę sys.excepthook.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from mailvoice.ui.ignore_dialog import IgnoreDialog


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("kind", ["ignore", "vip"])
def test_init_does_not_raise_into_excepthook(qapp, monkeypatch, kind):
    captured: list = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: captured.append(a))

    dialog = IgnoreDialog("ktos@firma.pl", "Faktura 123", kind=kind)

    assert captured == [], f"nieobsłużony wyjątek przy tworzeniu okna: {captured}"
    assert dialog._preview.text() != ""  # podgląd reguły ustawiony


def test_preview_updates_on_mode_change(qapp):
    dialog = IgnoreDialog("ktos@firma.pl", "Faktura 123")

    dialog._buttons["sender"].setChecked(True)
    sender_text = dialog._preview.text()
    dialog._buttons["domain"].setChecked(True)
    domain_text = dialog._preview.text()

    assert sender_text != ""
    assert domain_text != ""
    assert sender_text != domain_text  # różne tryby = różny podgląd


def test_mode_returns_selected(qapp):
    dialog = IgnoreDialog("ktos@firma.pl", "Faktura 123")
    dialog._buttons["domain"].setChecked(True)
    assert dialog.mode() == "domain"
