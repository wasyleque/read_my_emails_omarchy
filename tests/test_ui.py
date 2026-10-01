"""Testy jednostkowe i smoke-testy interfejsu użytkownika PySide6 (offscreen)."""

from datetime import datetime, timezone
from email.message import EmailMessage

import pytest
from PySide6.QtWidgets import QApplication

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import ProcessedMail
from mailvoice.core.service import MailService
from mailvoice.core.store import Store
from mailvoice.ui.main_window import MainWindow
from mailvoice.ui.settings import SettingsDialog
from mailvoice.ui.wizard import SetupWizard
from mailvoice.voice.tts import FakeSpeaker


class FakeSecretStore:
    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self.secrets.get(account)

    def set(self, account: str, secret: str) -> None:
        self.secrets[account] = secret

    def delete(self, account: str) -> None:
        self.secrets.pop(account, None)


@pytest.fixture(scope="session")
def qapp():
    """Zapewnia pojedynczą instancję QApplication dla całej sesji testowej."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_wizard_smoke_and_config_generation(qapp):
    """Smoke test kreatora SetupWizard: tworzenie okna i zbieranie AppConfig."""
    store = FakeSecretStore()
    speaker = FakeSpeaker()
    wizard = SetupWizard(secret_store=store, speaker=speaker)

    assert wizard.page_welcome is not None
    assert wizard.page_account is not None
    assert wizard.page_importance is not None

    # Symulacja wypełnienia pól przez użytkownika
    wizard.page_account.txt_email.setText("test@example.com")
    wizard.page_account.txt_password.setText("tajne_haslo")
    wizard.page_account.validatePage()
    assert store.get("test@example.com") == "tajne_haslo"

    # Ustawienie suwaka i szablonu
    wizard.page_importance.slider.setValue(8)
    wizard.page_importance.btn_work.click()
    wizard.page_importance.txt_vip_input.setText("boss@firma.pl")
    wizard.page_importance._add_vip()
    wizard.page_importance.txt_kw_input.setText("faktura, pilne")
    wizard.page_importance._add_kw()

    # Zbieranie konfiguracji
    cfg = wizard.get_app_config()
    assert isinstance(cfg, AppConfig)
    assert len(cfg.accounts) == 1
    assert cfg.accounts[0].username == "test@example.com"
    assert cfg.importance_threshold == 8
    assert "boss@firma.pl" in cfg.vip_senders
    assert "faktura" in cfg.keywords
    assert "pilne" in cfg.keywords
    assert cfg.notify_mode in ("beep", "ask")


def test_main_window_smoke_and_table(qapp, tmp_path):
    """Smoke test MainWindow: dodawanie maila do tabeli i akcje przycisków."""
    db_file = tmp_path / "test.db"
    store = Store(str(db_file))
    secret_store = FakeSecretStore()
    app_cfg = AppConfig(
        accounts=[AccountConfig(name="a1", host="imap.test.pl", username="a1")],
        importance_threshold=6,
    )
    service = MailService(
        config=app_cfg,
        store=store,
        secret_store=secret_store,
        ollama_client=OllamaClient(app_cfg.ollama),
    )
    speaker = FakeSpeaker()

    window = MainWindow(
        service=service,
        config_path=tmp_path / "config.json",
        speaker=speaker,
    )
    assert window.tbl_mails.rowCount() == 0

    # Dodanie ważnego maila
    msg = EmailMessage()
    msg["From"] = "klient@example.com"
    msg["Subject"] = "Oferta"
    parsed = ParsedMail(
        message_id="<m1@test>",
        sender="klient@example.com",
        subject="Oferta",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="Treść...",
    )
    processed = ProcessedMail(
        account="a1",
        folder="INBOX",
        uidvalidity=1,
        uid=1,
        mail=parsed,
        final_importance=9,
        rule_reasons=(),
        analysis_reason="Bardzo ważny klient",
        action="notify",
        language="pl",
    )

    window._add_important_mail(processed)
    assert window.tbl_mails.rowCount() == 1
    assert window.tbl_mails.item(0, 0).text() == "klient@example.com"
    assert window.tbl_mails.item(0, 1).text() == "Oferta"
    assert window.tbl_mails.item(0, 2).text() == "Bardzo ważny klient"

    # Wyciszenie
    assert window._is_muted is False
    window._toggle_mute()
    assert window._is_muted is True
    window._toggle_mute()
    assert window._is_muted is False


def test_settings_dialog_smoke(qapp, tmp_path, monkeypatch):
    """Smoke test SettingsDialog: zmiana parametrów i zapis do pliku."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(name="jan@firma.pl", host="imap.firma.pl", username="jan@firma.pl")
        ],
        importance_threshold=5,
    )
    secret_store = FakeSecretStore()

    saved_configs = []
    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        on_config_saved=lambda c: saved_configs.append(c),
    )

    dlg.slider.setValue(7)
    dlg.txt_desc.setText("Nowy opis reguł")
    dlg._on_save()

    assert len(saved_configs) == 1
    assert saved_configs[0].importance_threshold == 7
    assert saved_configs[0].analysis_prompt == "Nowy opis reguł"
    assert config_path.exists()
