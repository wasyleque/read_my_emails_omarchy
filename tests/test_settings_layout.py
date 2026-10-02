"""Długie pola formularzy mają się skalować z oknem, a nie pokazywać 3 linijek."""

import pytest
from PySide6.QtWidgets import QApplication

from mailvoice.core.config import AppConfig
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker


class _Secrets:
    def get(self, a):
        return None

    def set(self, a, s):
        pass

    def delete(self, a):
        pass


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path, width, height):
    dlg = SettingsDialog(
        config=AppConfig(),
        config_path=tmp_path / "c.json",
        secret_store=_Secrets(),
        speaker=FakeSpeaker(),
    )
    dlg.resize(width, height)
    dlg.show()
    QApplication.processEvents()
    dlg.tabs.setCurrentIndex(1)  # „Ważność”
    QApplication.processEvents()
    return dlg


def test_description_field_has_no_fixed_height_limit(qapp, tmp_path):
    dlg = _dialog(tmp_path, 900, 700)
    assert dlg.txt_desc.maximumHeight() > 10_000  # brak sztywnego limitu (domyślny Qt)


def test_description_grows_with_the_window(qapp, tmp_path):
    small = _dialog(tmp_path, 760, 520).txt_desc.height()
    large = _dialog(tmp_path, 760, 900).txt_desc.height()
    assert large > small + 150  # większe okno = wyraźnie większe pole
    assert large > 250  # w dużym oknie to nie są „3 linijki”


def test_description_keeps_a_readable_minimum_in_a_small_window(qapp, tmp_path):
    dlg = _dialog(tmp_path, 600, 380)
    assert dlg.txt_desc.height() >= 130  # mała rozdzielczość: strona się przewija, pole nie znika


def test_lists_have_no_fixed_maximum_height(qapp, tmp_path):
    dlg = _dialog(tmp_path, 900, 700)
    for widget in (dlg.list_vip, dlg.list_kw, dlg.list_ignore):
        assert widget.maximumHeight() > 10_000
