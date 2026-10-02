"""Testy zarządzania wieloma kontami w oknie Ustawień (SettingsDialog)."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker


class FakeSecretStore:
    """Prosty magazyn sekretów w pamięci do testów jednostkowych."""

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
    """Zapewnia pojedynczą instancję QApplication dla testów PySide6."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_accounts_list_add_edit_switch_preserve(qapp, tmp_path, monkeypatch):
    """Test dodawania, edycji i przełączania kont bez utraty wprowadzonych zmian."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(
                name="acc1@firma.pl",
                host="imap.firma.pl",
                username="acc1@firma.pl",
                port=993,
                use_ssl=True,
            )
        ]
    )
    secret_store = FakeSecretStore()
    secret_store.set("acc1@firma.pl", "HasloAcc1")

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    assert dlg.list_accounts.count() == 1
    assert dlg.txt_email.text() == "acc1@firma.pl"

    # Dodanie drugiego konta
    dlg.btn_add_account.click()
    assert dlg.list_accounts.count() == 2
    assert dlg.list_accounts.currentRow() == 1

    # Wypełnienie formularza drugiego konta
    dlg.txt_email.setText("acc2@gmail.com")
    dlg.txt_password.setText("HasloAcc2")
    dlg.txt_host.setText("imap.gmail.com")
    dlg.txt_port.setText("993")
    dlg.txt_sent_folder.setText("[Gmail]/Sent Mail")

    # Przełączenie na konto 1
    dlg.list_accounts.setCurrentRow(0)
    assert dlg.txt_email.text() == "acc1@firma.pl"
    assert dlg.txt_host.text() == "imap.firma.pl"

    # Przełączenie z powrotem na konto 2 - wartości muszą być zachowane
    dlg.list_accounts.setCurrentRow(1)
    assert dlg.txt_email.text() == "acc2@gmail.com"
    assert dlg.txt_password.text() == "HasloAcc2"
    assert dlg.txt_host.text() == "imap.gmail.com"
    assert dlg.txt_sent_folder.text() == "[Gmail]/Sent Mail"


def test_account_blank_password_does_not_overwrite(qapp, tmp_path, monkeypatch):
    """Pozostawienie pustego hasła przy edycji konta nie nadpisuje hasła w sejfie."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(
                name="user@example.com",
                host="imap.example.com",
                username="user@example.com",
                port=993,
            )
        ]
    )
    secret_store = FakeSecretStore()
    secret_store.set("user@example.com", "SuperTajneHaslo123")

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    # Pole hasła powinno być puste (z placeholderem)
    assert dlg.txt_password.text() == ""
    # Zmiana innego pola np. folderu wysłanych
    dlg.txt_sent_folder.setText("Elementy wyslane")
    dlg._on_save()

    # Hasło w sejfie nie może ulec zmianie ani skasowaniu
    assert secret_store.get("user@example.com") == "SuperTajneHaslo123"


def test_account_rename_migrates_secret(qapp, tmp_path, monkeypatch):
    """Zmiana adresu/nazwy konta migruje hasło pod nową nazwę i usuwa stary wpis."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(
                name="stary_adres@firma.pl",
                host="imap.firma.pl",
                username="stary_adres@firma.pl",
            )
        ]
    )
    secret_store = FakeSecretStore()
    secret_store.set("stary_adres@firma.pl", "TajneHasloStare")

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    # Zmiana nazwy / emaila bez wpisywania nowego hasła
    dlg.txt_email.setText("nowy_adres@firma.pl")
    dlg._on_save()

    # Nowy adres powinien mieć przeniesione hasło, stary powinien być skasowany
    assert secret_store.get("nowy_adres@firma.pl") == "TajneHasloStare"
    assert secret_store.get("stary_adres@firma.pl") is None


def test_account_remove_deletes_secret(qapp, tmp_path, monkeypatch):
    """Usunięcie konta kasuje powiązany sekret z SecretStore."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(name="konto1@firma.pl", host="imap.firma.pl", username="konto1@firma.pl"),
            AccountConfig(
                name="konto2@do_usuniecia.pl",
                host="imap.do_usuniecia.pl",
                username="konto2@do_usuniecia.pl",
            ),
        ]
    )
    secret_store = FakeSecretStore()
    secret_store.set("konto1@firma.pl", "Haslo1")
    secret_store.set("konto2@do_usuniecia.pl", "Haslo2DoUsuniecia")

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    assert dlg.list_accounts.count() == 2
    # Wybór konta 2 i usunięcie
    dlg.list_accounts.setCurrentRow(1)
    dlg.btn_remove_account.click()
    assert dlg.list_accounts.count() == 1

    dlg._on_save()

    # Konto 1 pozostaje w sejfie, konto 2 zostało usunięte
    assert secret_store.get("konto1@firma.pl") == "Haslo1"
    assert secret_store.get("konto2@do_usuniecia.pl") is None


def test_account_duplicate_validation(qapp, tmp_path, monkeypatch):
    """Próba dodania dwóch kont o takim samym adresie wywołuje ostrzeżenie i blokuje zapis."""
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)

    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(
                name="duplikat@firma.pl", host="imap.firma.pl", username="duplikat@firma.pl"
            )
        ]
    )
    secret_store = FakeSecretStore()

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    # Dodanie drugiego konta o identycznym adresie
    dlg.btn_add_account.click()
    dlg.txt_email.setText("duplikat@firma.pl")

    dlg._on_save()

    assert len(warnings) > 0
    # Plik konfiguracyjny nie powinien zostać zapisany z duplikatem
    assert not config_path.exists()


def test_account_invalid_port_and_ssl_validation(qapp, tmp_path, monkeypatch):
    """Walidacja zakresu portu (1-65535) oraz wymóg włączonego SSL/TLS."""
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)

    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(name="user@firma.pl", host="imap.firma.pl", username="user@firma.pl")
        ]
    )
    secret_store = FakeSecretStore()

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    # 1. Błędny port
    dlg.txt_port.setText("99999")
    dlg._on_save()
    assert len(warnings) == 1
    assert not config_path.exists()

    # 2. Poprawny port, ale wyłączony SSL
    warnings.clear()
    dlg.txt_port.setText("993")
    dlg.chk_ssl.setChecked(False)
    dlg._on_save()
    assert len(warnings) == 1
    assert not config_path.exists()


def test_save_preserves_other_settings(qapp, tmp_path, monkeypatch):
    """Zapis kont nie nadpisuje pozostałych ustawień domyślnymi wartościami."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[AccountConfig(name="a1@firma.pl", host="imap.firma.pl", username="a1@firma.pl")],
        analysis_prompt="Ważne: tylko maile z załącznikami PDF",
        vip_senders=["prezes@firma.pl"],
        keywords=["faktura", "umowa"],
        interval_minutes=15,
        notify_mode="ask",
        importance_threshold=8,
        digest_days=45,
        language="pl",
        index_retention_days=180,
    )
    secret_store = FakeSecretStore()

    saved_list = []
    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        on_config_saved=lambda c: saved_list.append(c),
        speaker=FakeSpeaker(),
    )

    # Dodanie drugiego konta
    dlg.btn_add_account.click()
    dlg.txt_email.setText("a2@firma.pl")
    dlg.txt_host.setText("imap.a2.pl")
    dlg._on_save()

    assert len(saved_list) == 1
    c = saved_list[0]
    assert len(c.accounts) == 2
    assert c.analysis_prompt == "Ważne: tylko maile z załącznikami PDF"
    assert c.vip_senders == ["prezes@firma.pl"]
    assert c.keywords == ["faktura", "umowa"]
    assert c.interval_minutes == 15
    assert c.notify_mode == "ask"
    assert c.importance_threshold == 8
    assert c.digest_days == 45
    assert c.language == "pl"
    assert c.index_retention_days == 180


def test_settings_dialog_offscreen_screenshot(qapp, tmp_path, monkeypatch):
    """Smoke test okna Ustawień z trzema kontami i zrzut ekranu (docs/screenshots)."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(
                name="jan.kowalski@firma.pl",
                host="imap.gmail.com",
                username="jan.kowalski@firma.pl",
                port=993,
                sent_folder="[Gmail]/Sent Mail",
            ),
            AccountConfig(
                name="biuro@wlasny-serwer.pl",
                host="mail.wlasny-serwer.pl",
                username="biuro@wlasny-serwer.pl",
                port=993,
                sent_folder="Sent",
            ),
            AccountConfig(
                name="prywatny@onet.pl",
                host="imap.poczta.onet.pl",
                username="prywatny@onet.pl",
                port=993,
                sent_folder="Wysłane",
            ),
        ],
        importance_threshold=7,
        analysis_prompt="Priorytet: pilne wiadomości od klientów i faktury.",
        vip_senders=["zarzad@firma.pl", "ksiegowosc@firma.pl"],
        keywords=["faktura", "pilne", "awaria"],
        notify_mode="ask",
        interval_minutes=10,
    )
    secret_store = FakeSecretStore()
    secret_store.set("jan.kowalski@firma.pl", "fake_pwd_1")
    secret_store.set("biuro@wlasny-serwer.pl", "fake_pwd_2")
    secret_store.set("prywatny@onet.pl", "fake_pwd_3")

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    dlg.show()
    qapp.processEvents()

    assert dlg.list_accounts.count() == 3

    # Zrzut ekranu zakładki Konta: domyślnie do katalogu tymczasowego (test nie modyfikuje repo);
    # aby odświeżyć zrzut w dokumentacji: MAILVOICE_UPDATE_SCREENSHOTS=1 pytest ...
    update_docs = os.environ.get("MAILVOICE_UPDATE_SCREENSHOTS") == "1"
    screenshot_dir = Path("docs/screenshots") if update_docs else tmp_path
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / "settings_accounts.png"

    pixmap = dlg.grab()
    saved = pixmap.save(str(screenshot_path))
    dlg.close()

    assert saved is True
    assert screenshot_path.exists()
    assert screenshot_path.stat().st_size > 0
