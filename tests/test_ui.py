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


def test_main_window_digest_tab_smoke(qapp):
    """Smoke test zakładki Podsumowanie w MainWindow oraz odtwarzania tematu."""
    from mailvoice.core.digest import Digest, Participant, Topic

    speaker = FakeSpeaker()
    window = MainWindow(speaker=speaker)

    assert window.tabs.count() == 2
    assert window.tabs.tabText(0) == "Wiadomości"
    assert window.tabs.tabText(1) == "Podsumowanie tematów"

    topic = Topic(
        title="Oferta sprzętu biurowego",
        participants=[Participant(address="sales@biuro.pl", role="from", count=1)],
        who_to_whom=["sales@biuro.pl -> me@corp.com"],
        why="Przesłanie zaktualizowanego cennika laptopów.",
        status="oczekuje_na_mnie",
        last_activity=datetime.now(timezone.utc),
        importance=8,
        mail_count=1,
    )
    digest = Digest(period="ostatnie 30 dni", topics=[topic])

    window._display_digest(digest)
    assert window.digest_layout.count() > 0

    window._listen_to_topic(topic)
    assert len(speaker.spoken) > 0
    assert "Oferta sprzętu biurowego" in speaker.spoken[-1][0]


def test_main_window_context_panel_smoke(qapp):
    """Smoke test panelu kontekstu kontaktu w oknie głównym."""
    from mailvoice.core.contacts import ContactCard

    speaker = FakeSpeaker()
    window = MainWindow(speaker=speaker)

    assert hasattr(window, "group_context")
    assert hasattr(window, "btn_ai_search")

    # Dodanie wiadomości
    item = ProcessedMail(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=1,
        mail=ParsedMail(
            message_id="<m1@test>",
            sender="Piotr Kowalski <kowalski@budowa.pl>",
            subject="Faktura remontowa",
            date=datetime.now(timezone.utc),
            in_reply_to=None,
            references=(),
            body_text="Treść maila...",
        ),
        final_importance=8,
        rule_reasons=(),
        analysis_reason="Ważna płatność",
        action="read_now",
        language="pl",
    )
    window._add_important_mail(item)
    assert window.tbl_mails.rowCount() == 1

    # 1. Wyświetlenie nieznanego kontaktu
    window._display_contact_card(None, item.mail.sender)
    assert "Nie znam jeszcze tego nadawcy" in window.lbl_context_details.text()
    assert window.btn_context_search.isEnabled()

    # 2. Wyświetlenie znanej karty kontaktu
    card = ContactCard(
        name="Piotr Kowalski",
        addresses=("kowalski@budowa.pl",),
        first_seen=datetime.now(timezone.utc),
        last_contact=datetime.now(timezone.utc),
        mail_count=5,
        topics=[],
        open_items=["Zatwierdzenie faktury 45/2026"],
        last_exchange=[(datetime.now(timezone.utc), "odebrany", "Faktura za remont biura")],
        relationship_hint="Główny wykonawca remontu",
        why_it_matters="Płatność za prace wykończeniowe",
    )
    window._display_contact_card(card, item.mail.sender)
    assert "Piotr Kowalski" in window.lbl_context_details.text()
    assert "Główny wykonawca remontu" in window.lbl_context_details.text()
    assert "Zatwierdzenie faktury" in window.lbl_context_details.text()
    assert window.btn_context_search.isEnabled()


def test_search_dialog_smoke(qapp):
    """Smoke test okna dialogowego wyszukiwania AI."""
    from mailvoice.core.aisearch import MailRef, SearchHit
    from mailvoice.ui.search_dialog import SearchDialog

    speaker = FakeSpeaker()
    dlg = SearchDialog(speaker=speaker)

    assert dlg.txt_query is not None
    assert dlg.cb_period.count() == 3

    # Brak wyników
    dlg._display_hits([])
    assert "Nie znaleziono pasujących wiadomości" in dlg.results_layout.itemAt(0).widget().text()

    # Wynik z wysoką pewnością
    hit = SearchHit(
        mail_ref=MailRef(
            account="acc1",
            folder="INBOX",
            uidvalidity=1,
            uid=42,
            message_id="<m42@test>",
            subject="Faktura VAT 12/2026",
            sender="Księgowość <ksiegowosc@firma.pl>",
            date="2026-10-01",
        ),
        score=0.95,
        why_probable="Zgadza się numer faktury i temat.",
        snippet="Faktura za usługi informatyczne.",
        confidence="wysoka",
    )
    dlg._display_hits([hit])
    assert dlg.results_layout.count() >= 2  # card + stretch

    # Posłuchaj wyniku
    dlg._listen_to_hit(hit)
    assert len(speaker.spoken) > 0
    assert "Faktura VAT 12/2026" in speaker.spoken[-1][0]


def test_account_page_details_toggle(qapp):
    """Test rozwinięcia i ukrywania szczegółów technicznych w kreatorze."""
    from mailvoice.ui.wizard import AccountPage

    sec_store = FakeSecretStore()
    page = AccountPage(secret_store=sec_store)
    page.show()

    assert not page.btn_details.isVisible()
    assert not page.txt_details.isVisible()

    page._on_test_error("Coś poszło nie tak.", "Typ błędu: FetchError\nSzczegóły: connection reset")
    assert page.btn_details.isVisible()
    assert not page.txt_details.isVisible()
    assert "Szczegóły" in page.btn_details.text()

    page._toggle_details()
    assert page.txt_details.isVisible()
    assert "FetchError" in page.txt_details.toPlainText()
    assert "Ukryj" in page.btn_details.text()

    page._toggle_details()
    assert not page.txt_details.isVisible()

    page._on_input_changed()
    assert not page.btn_details.isVisible()
    assert not page.txt_details.isVisible()
    page.close()


def test_settings_dialog_details_toggle(qapp, tmp_path):
    """Test testowania połączenia i rozwinięcia szczegółów w oknie ustawień."""
    sec_store = FakeSecretStore()
    cfg = AppConfig()
    cfg_file = tmp_path / "config.json"
    dlg = SettingsDialog(cfg, cfg_file, sec_store)
    dlg.show()

    assert hasattr(dlg, "btn_test")
    assert hasattr(dlg, "btn_details")
    assert hasattr(dlg, "txt_details")
    assert not dlg.btn_details.isVisible()
    assert not dlg.txt_details.isVisible()

    dlg._on_test_error("Błąd połączenia.", "Typ błędu: TimeoutError\nSzczegóły: timeout 30s")
    assert dlg.btn_details.isVisible()
    assert not dlg.txt_details.isVisible()

    dlg._toggle_details()
    assert dlg.txt_details.isVisible()
    assert "TimeoutError" in dlg.txt_details.toPlainText()

    dlg._on_account_input_changed()
    assert not dlg.btn_details.isVisible()
    assert not dlg.txt_details.isVisible()
    dlg.close()


def test_error_shows_details_button_with_raw_message(qapp):
    """Regresja: komunikat obiecywał „kliknij Szczegóły”, a przycisku w oknie głównym nie było."""
    window = MainWindow(speaker=FakeSpeaker())
    assert not window.btn_error_details.isVisibleTo(window)
    window._show_problem("Serwery AI zawiodły: http://x:11434 -> HTTP 404 (model nie znaleziony)")
    assert window.btn_error_details.isVisibleTo(window)
    assert "HTTP 404" in window._last_error_details
    assert "model AI" in window.lbl_status.text()  # prosty komunikat po ludzku
