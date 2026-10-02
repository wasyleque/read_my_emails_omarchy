"""Testy zakładki Telefon (Android) oraz okna parowania w GUI."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.ui.main_window import MainWindow
from mailvoice.ui.pairing_dialog import PairingDialog
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker


@pytest.fixture(scope="session")
def qapp():
    """Zapewnia pojedynczą instancję QApplication dla testów PySide6."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeSecretStore:
    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self.secrets.get(account)

    def set(self, account: str, secret: str) -> None:
        self.secrets[account] = secret

    def delete(self, account: str) -> None:
        self.secrets.pop(account, None)


def test_settings_dialog_mobile_tab_and_save(qapp, tmp_path: Path, monkeypatch):
    """Weryfikuje obecność zakładki Telefon, przełącznik i zapis konfiguracji."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    cfg_file = tmp_path / "config.json"
    cfg = AppConfig()
    cfg.server.enabled = False

    db_file = tmp_path / "test.db"
    dev_mgr = DeviceManager(db_file)
    sec_store = FakeSecretStore()

    saved_configs: list[AppConfig] = []

    dlg = SettingsDialog(
        config=cfg,
        config_path=cfg_file,
        secret_store=sec_store,
        speaker=FakeSpeaker(),
        on_config_saved=lambda c: saved_configs.append(c),
        device_manager=dev_mgr,
        data_dir=tmp_path,
    )

    # 1. Sprawdzenie liczby i tytułu zakładki
    assert dlg.tabs.count() == 5
    assert "Telefon" in dlg.tabs.tabText(4)

    # 2. Stan początkowy przełącznika (wyłączony)
    assert not dlg.cb_server_enabled.isChecked()
    assert not dlg.btn_pair.isEnabled()
    assert "wyłączone" in dlg.lbl_server_status.text()

    # 3. Włączenie serwera w UI
    dlg.cb_server_enabled.setChecked(True)
    assert dlg.cb_server_enabled.isChecked()
    assert dlg.btn_pair.isEnabled()
    assert "https://" in dlg.lbl_server_status.text() or "Brak" in dlg.lbl_server_status.text()

    # 4. Zapis konfiguracji
    dlg._on_save()
    assert len(saved_configs) == 1
    assert saved_configs[0].server.enabled is True

    dlg.close()


def test_settings_dialog_devices_list_and_revocation(qapp, tmp_path: Path, monkeypatch):
    """Weryfikuje listę urządzeń oraz potwierdzenie i odwołanie urządzenia."""
    db_file = tmp_path / "test.db"
    dev_mgr = DeviceManager(db_file)
    sec_store = FakeSecretStore()

    # Dodanie sparowanego urządzenia
    session = dev_mgr.start_pairing_session()
    dev, _ = dev_mgr.pair_device(session.code, "Testowy Telefon Poco")

    cfg_file = tmp_path / "config.json"
    cfg = AppConfig()
    cfg.server.enabled = True

    # Mock potwierdzenia w oknie dialogowym pytania (Yes)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    dlg = SettingsDialog(
        config=cfg,
        config_path=cfg_file,
        secret_store=sec_store,
        device_manager=dev_mgr,
        data_dir=tmp_path,
    )

    # Lista zawiera jedno urządzenie
    assert dlg.list_devices.count() == 1
    assert "Testowy Telefon Poco" in dlg.list_devices.item(0).text()

    # Wybór urządzenia aktywuje przycisk "Odłącz"
    assert not dlg.btn_revoke_device.isEnabled()
    dlg.list_devices.setCurrentRow(0)
    assert dlg.btn_revoke_device.isEnabled()

    # Odłączenie urządzenia
    dlg._on_revoke_device()

    # Urządzenie odwołane w bazie
    devices = dev_mgr.list_devices(include_revoked=False)
    assert len(devices) == 0

    dlg.close()


def test_pairing_dialog_qr_and_timer(qapp, tmp_path: Path):
    """Weryfikuje generowanie kodu QR, kod tekstowy oraz odliczanie czasu."""
    db_file = tmp_path / "test.db"
    dev_mgr = DeviceManager(db_file)

    dlg = PairingDialog(
        device_manager=dev_mgr,
        port=8765,
        data_dir=tmp_path,
        bind_host="192.168.1.100",
    )

    # 1. Wygenerowany kod tekstowy
    assert len(dlg.session.code) == 6
    assert dlg.lbl_code.text() == dlg.session.code

    # 2. Wygenerowany kod QR
    pixmap = dlg.lbl_qr.pixmap()
    assert not pixmap.isNull()
    assert pixmap.width() > 50

    # 3. Odliczanie czasu
    assert dlg.remaining_seconds == 120
    dlg._on_tick()
    assert dlg.remaining_seconds == 119
    assert "119" in dlg.lbl_timer.text()

    # 4. Wygaśnięcie po upływie czasu
    dlg.remaining_seconds = 1
    dlg._on_tick()
    assert dlg.remaining_seconds == 0
    assert not dlg.timer.isActive()
    assert not dlg.lbl_qr.isEnabled()

    dlg.close()


def test_main_window_mobile_indicator(qapp, tmp_path: Path):
    """Weryfikuje wskaźnik serwera mobilnego w oknie głównym."""
    sec_store = FakeSecretStore()

    cfg = AppConfig()
    cfg.server.enabled = False

    fake_service = MagicMock()
    fake_service.config = cfg
    fake_service.store = MagicMock()
    fake_service.secret_store = sec_store
    fake_service.add_listener = MagicMock()

    win = MainWindow(
        service=fake_service,
        config_path=tmp_path / "config.json",
    )

    # Przy wyłączonym serwerze wskaźnik jest ukryty
    assert not win.lbl_mobile_indicator.isVisible()

    win.close()
