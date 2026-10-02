"""Regresja: kod QR nie może być pokazany, gdy serwer dla telefonu nie działa."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.ui import settings as settings_mod
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker


class _Secrets:
    def get(self, account):
        return None

    def set(self, account, secret):
        pass

    def delete(self, account):
        pass


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path: Path, server_status):
    return SettingsDialog(
        config=AppConfig(),
        config_path=tmp_path / "config.json",
        secret_store=_Secrets(),
        speaker=FakeSpeaker(),
        device_manager=DeviceManager(tmp_path / "d.db"),
        data_dir=tmp_path,
        server_status=server_status,
    )


@pytest.fixture
def opened(monkeypatch):
    """Rejestruje, czy okno parowania zostało otwarte, oraz komunikaty dla użytkownika."""
    state = {"pairing": 0, "messages": []}

    class FakePairing:
        def __init__(self, *a, **k):
            state["pairing"] += 1

        def exec(self):
            return 0

    monkeypatch.setattr(settings_mod, "PairingDialog", FakePairing)
    for name in ("information", "warning"):
        monkeypatch.setattr(
            QMessageBox, name, lambda *a, _n=name, **k: state["messages"].append((_n, a[2]))
        )
    return state


def test_pairing_refused_when_phone_connection_not_enabled(qapp, tmp_path, opened):
    dlg = _dialog(tmp_path, server_status=lambda: (True, ""))
    dlg.cb_server_enabled.setChecked(False)
    dlg._on_pair_device()
    assert opened["pairing"] == 0
    assert opened["messages"] and "Włącz" in opened["messages"][0][1]


def test_pairing_refused_when_server_not_running_and_shows_reason(qapp, tmp_path, opened):
    dlg = _dialog(tmp_path, server_status=lambda: (False, "OSError: adres zajęty"))
    dlg.cb_server_enabled.setChecked(True)
    dlg._on_pair_device()
    assert opened["pairing"] == 0
    assert "adres zajęty" in opened["messages"][0][1]
    assert "Zapisz zmiany" in opened["messages"][0][1]


def test_pairing_allowed_when_server_running(qapp, tmp_path, opened):
    dlg = _dialog(tmp_path, server_status=lambda: (True, ""))
    dlg.cb_server_enabled.setChecked(True)
    dlg._on_pair_device()
    assert opened["pairing"] == 1
