"""Kreator pierwszego uruchomienia aplikacji MailVoice."""

from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from mailvoice.core.analyzer import fetch_ollama_models
from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig
from mailvoice.core.friendly_errors import format_friendly_error_ex
from mailvoice.core.imap_fetch import ImapToolsClient
from mailvoice.core.ollama_models import suggest_models
from mailvoice.core.providers import get_provider_by_id, get_providers
from mailvoice.core.secrets import SecretStore
from mailvoice.ui import theme
from mailvoice.ui.i18n import get_language, set_language, tr
from mailvoice.voice.tts import FakeSpeaker, PiperSpeaker, Speaker, VoiceUnavailable


class ImapTestWorker(QThread):
    """Wątek sprawdzania połączenia ze skrzynką IMAP."""

    finished_ok = Signal()
    finished_error = Signal(str, str)

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        lang: str = "pl",
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.lang = lang

    def run(self) -> None:
        try:
            client = ImapToolsClient(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                use_ssl=self.use_ssl,
            )
            try:
                # Logowanie dzieje się przy pierwszym zapytaniu; sprawdzamy też dostęp do INBOX.
                client.get_uidvalidity("INBOX")
            finally:
                client.close()
            self.finished_ok.emit()
        except Exception as exc:
            msg, details = format_friendly_error_ex(exc, lang=self.lang)
            self.finished_error.emit(msg, details)


class WelcomePage(QWizardPage):
    """Krok 1: Powitanie i wybór języka."""

    def __init__(self, on_lang_change: Callable[[str], None]) -> None:
        super().__init__()
        self.on_lang_change = on_lang_change
        self._init_ui()

    def _init_ui(self) -> None:
        self.setTitle(tr("step1_title"))
        layout = QVBoxLayout(self)

        intro = QLabel(tr("step1_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addSpacing(20)

        lang_label = QLabel(tr("step1_lang_label"))
        layout.addWidget(lang_label)

        self.rb_pl = QRadioButton("Polski (PL)")
        self.rb_en = QRadioButton("English (EN)")
        if get_language() == "en":
            self.rb_en.setChecked(True)
        else:
            self.rb_pl.setChecked(True)

        self.rb_pl.toggled.connect(self._on_pl_toggled)
        layout.addWidget(self.rb_pl)
        layout.addWidget(self.rb_en)
        layout.addStretch()

    def _on_pl_toggled(self, checked: bool) -> None:
        lang = "pl" if checked else "en"
        set_language(lang)
        self.on_lang_change(lang)


class AccountPage(QWizardPage):
    """Krok 2: Dodanie konta pocztowego IMAP."""

    def __init__(self, secret_store: SecretStore) -> None:
        super().__init__()
        self.secret_store = secret_store
        self.worker: ImapTestWorker | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        self.setTitle(tr("step2_title"))
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Wybór dostawcy
        self.cb_provider = QComboBox()
        self.providers = get_providers()
        for p in self.providers:
            self.cb_provider.addItem(p.display_name, p.provider_id)
        self.cb_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(tr("step2_provider"), self.cb_provider)

        # Adres e-mail
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("jan.kowalski@example.com")
        self.txt_email.textChanged.connect(self._on_input_changed)
        form.addRow(tr("step2_email"), self.txt_email)

        # Hasło
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("••••••••")
        form.addRow(tr("step2_password"), self.txt_password)

        layout.addLayout(form)

        # Podpowiedź dla dostawcy (np. hasło aplikacji Gmail)
        self.lbl_help = QLabel()
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        layout.addWidget(self.lbl_help)

        # Przycisk sprawdzania połączenia i etykieta wyniku
        test_container = QVBoxLayout()
        test_row = QHBoxLayout()
        self.btn_test = QPushButton(tr("step2_test_btn"))
        self.btn_test.clicked.connect(self._on_test_connection)
        test_row.addWidget(self.btn_test)

        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        test_row.addWidget(self.lbl_test_result)
        test_row.addStretch()
        test_container.addLayout(test_row)

        self.btn_details = QPushButton(tr("btn_details"))
        self.btn_details.setVisible(False)
        self.btn_details.clicked.connect(self._toggle_details)
        test_container.addWidget(self.btn_details, alignment=Qt.AlignmentFlag.AlignLeft)

        self.txt_details = QTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setMaximumHeight(90)
        self.txt_details.setVisible(False)
        test_container.addWidget(self.txt_details)

        layout.addLayout(test_container)

        # Sekcja zaawansowana (zwijana / opcjonalna)
        self.advanced_box = QGroupBox(tr("step2_advanced"))
        self.advanced_box.setCheckable(True)
        self.advanced_box.setChecked(False)
        adv_form = QFormLayout(self.advanced_box)

        self.txt_host = QLineEdit()
        adv_form.addRow(tr("step2_host"), self.txt_host)

        self.txt_port = QLineEdit("993")
        adv_form.addRow(tr("step2_port"), self.txt_port)

        self.chk_ssl = QCheckBox("SSL / TLS")
        self.chk_ssl.setChecked(True)
        adv_form.addRow("", self.chk_ssl)

        layout.addWidget(self.advanced_box)

        self.lbl_multi_hint = QLabel(tr("step2_multi_hint"))
        self.lbl_multi_hint.setWordWrap(True)
        self.lbl_multi_hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        layout.addWidget(self.lbl_multi_hint)

        layout.addStretch()

        self._on_provider_changed(0)

    def _toggle_details(self) -> None:
        visible = not self.txt_details.isVisible()
        self.txt_details.setVisible(visible)
        self.btn_details.setText(tr("btn_hide_details") if visible else tr("btn_details"))

    def _on_provider_changed(self, index: int) -> None:
        p_id = self.cb_provider.currentData()
        provider = get_provider_by_id(p_id)
        self.txt_host.setText(provider.host)
        self.txt_port.setText(str(provider.port))
        self.chk_ssl.setChecked(provider.use_ssl)

        lang = get_language()
        help_text = provider.help_text_pl if lang == "pl" else provider.help_text_en
        self.lbl_help.setText(help_text)

    def _on_input_changed(self) -> None:
        self.lbl_test_result.setText("")
        self.btn_details.setVisible(False)
        self.txt_details.setVisible(False)

    def _on_test_connection(self) -> None:
        host = self.txt_host.text().strip()
        port_str = self.txt_port.text().strip()
        try:
            port = int(port_str)
        except ValueError:
            port = 993
        username = self.txt_email.text().strip()
        password = self.txt_password.text()

        self.btn_test.setEnabled(False)
        self.btn_details.setVisible(False)
        self.txt_details.setVisible(False)
        self.lbl_test_result.setStyleSheet(f"color: {theme.c('accent')};")
        self.lbl_test_result.setText(tr("step2_test_testing"))

        self.worker = ImapTestWorker(
            host=host,
            port=port,
            username=username,
            password=password,
            use_ssl=self.chk_ssl.isChecked(),
            lang=get_language(),
        )
        self.worker.finished_ok.connect(self._on_test_ok)
        self.worker.finished_error.connect(self._on_test_error)
        self.worker.start()

    def _on_test_ok(self) -> None:
        self.btn_test.setEnabled(True)
        self.lbl_test_result.setStyleSheet(f"color: {theme.c('ok')}; font-weight: bold;")
        self.lbl_test_result.setText(tr("step2_test_ok"))
        self.btn_details.setVisible(False)
        self.txt_details.setVisible(False)

    def _on_test_error(self, message: str, details: str = "") -> None:
        self.btn_test.setEnabled(True)
        self.lbl_test_result.setStyleSheet(f"color: {theme.c('error')};")
        self.lbl_test_result.setText(message)
        if details:
            self.txt_details.setPlainText(details)
            self.btn_details.setText(tr("btn_details"))
            self.btn_details.setVisible(True)
            self.txt_details.setVisible(False)
        else:
            self.btn_details.setVisible(False)
            self.txt_details.setVisible(False)

    def validatePage(self) -> bool:
        email = self.txt_email.text().strip()
        if not email:
            QMessageBox.warning(
                self,
                "MailVoice",
                "Podaj adres e-mail." if get_language() == "pl" else "Enter email address.",
            )
            return False
        # Zapisujemy hasło do SecretStore
        pwd = self.txt_password.text()
        if pwd:
            self.secret_store.set(email, pwd)
        return True

    def get_account_config(self) -> AccountConfig:
        email = self.txt_email.text().strip()
        p_id = self.cb_provider.currentData()
        provider = get_provider_by_id(p_id)
        host = self.txt_host.text().strip() or provider.host
        try:
            port = int(self.txt_port.text().strip())
        except ValueError:
            port = 993
        return AccountConfig(
            name=email,
            host=host,
            port=port,
            username=email,
            use_ssl=self.chk_ssl.isChecked(),
            folders=["INBOX"],
            sent_folder=provider.sent_folder,
        )


class OllamaPage(QWizardPage):
    """Krok 3: Wykrywanie i wybór modelu Ollama."""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setTitle(tr("step3_title"))
        layout = QVBoxLayout(self)

        desc = QLabel(tr("step3_desc"))
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(10)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        form = QFormLayout()
        self.cb_model = QComboBox()
        form.addRow(tr("step3_model_label"), self.cb_model)
        layout.addLayout(form)

        self.lbl_guide = QLabel(tr("step3_install_guide"))
        self.lbl_guide.setWordWrap(True)
        self.lbl_guide.setStyleSheet(
            f"color: {theme.c('text')}; background: {theme.c('guide_bg')}; padding: 8px;"
        )
        layout.addWidget(self.lbl_guide)

        # Zaawansowane (URL)
        self.adv_group = QGroupBox(tr("step3_advanced_url"))
        self.adv_group.setCheckable(True)
        self.adv_group.setChecked(False)
        adv_form = QFormLayout(self.adv_group)
        self.txt_local_url = QLineEdit("http://127.0.0.1:11434")
        self.txt_lan_url = QLineEdit("http://192.168.1.50:11434")
        adv_form.addRow("Local URL:", self.txt_local_url)
        adv_form.addRow("LAN URL:", self.txt_lan_url)
        # zmiana adresu = ponowne wykrycie modeli
        self.txt_lan_url.editingFinished.connect(self._detect_ollama)
        self.txt_local_url.editingFinished.connect(self._detect_ollama)
        layout.addWidget(self.adv_group)

        layout.addStretch()

    def initializePage(self) -> None:
        self._detect_ollama()

    def _detect_ollama(self) -> None:
        local_models = self._fetch_models(self.txt_local_url.text().strip())
        self._detected_local = bool(local_models)
        models = local_models or self._fetch_models(self.txt_lan_url.text().strip())
        self._suggestion = suggest_models(models)

        self.cb_model.clear()
        if self._suggestion.choices:
            self.lbl_status.setStyleSheet(f"color: {theme.c('ok')}; font-weight: bold;")
            self.lbl_status.setText(tr("step3_detected"))
            self.lbl_guide.setVisible(False)
            for m in self._suggestion.choices:
                self.cb_model.addItem(m)  # zalecane na górze; tylko zainstalowane, bez chmurowych
        else:
            self.lbl_status.setStyleSheet(f"color: {theme.c('warn')}; font-weight: bold;")
            self.lbl_status.setText(tr("step3_not_detected"))
            self.lbl_guide.setVisible(True)
            self.adv_group.setChecked(True)  # pokaż pole adresu serwera, żeby można było go wpisać
            self.cb_model.addItem("qwen3:8b")
            self.cb_model.addItem("qooba/bielik-11b-v3.0-instruct")

    def _fetch_models(self, url: str) -> list[str]:
        return fetch_ollama_models(url)

    def get_ollama_config(self) -> OllamaConfig:
        model = self.cb_model.currentText() or "qwen3:8b"
        suggestion = getattr(self, "_suggestion", None)
        polish = (suggestion.polish if suggestion else None) or model
        return OllamaConfig(
            lan_url=self.txt_lan_url.text().strip(),
            local_url=self.txt_local_url.text().strip(),
            model=model,
            polish_model=polish,
            prefer="local" if getattr(self, "_detected_local", False) else "lan",
        )


class ImportancePage(QWizardPage):
    """Krok 4: Opis co jest ważne, suwak oceny, listy VIP i słów."""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setTitle(tr("step4_title"))
        layout = QVBoxLayout(self)

        # Szablony
        tmpl_layout = QHBoxLayout()
        tmpl_label = QLabel(tr("step4_templates_label"))
        tmpl_layout.addWidget(tmpl_label)

        self.btn_work = QPushButton(tr("template_work"))
        self.btn_home = QPushButton(tr("template_home"))
        self.btn_biz = QPushButton(tr("template_business"))
        self.btn_work.clicked.connect(lambda: self.txt_desc.setText(tr("template_work_text")))
        self.btn_home.clicked.connect(lambda: self.txt_desc.setText(tr("template_home_text")))
        self.btn_biz.clicked.connect(lambda: self.txt_desc.setText(tr("template_business_text")))
        tmpl_layout.addWidget(self.btn_work)
        tmpl_layout.addWidget(self.btn_home)
        tmpl_layout.addWidget(self.btn_biz)
        tmpl_layout.addStretch()
        layout.addLayout(tmpl_layout)

        # Pole opisu
        layout.addWidget(QLabel(tr("step4_desc_label")))
        self.txt_desc = QTextEdit()
        self.txt_desc.setPlainText(tr("template_work_text"))
        self.txt_desc.setMaximumHeight(80)
        layout.addWidget(self.txt_desc)

        # Suwak ostrości oceny
        layout.addWidget(QLabel(tr("step4_threshold_label")))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 10)
        self.slider.setValue(6)
        layout.addWidget(self.slider)

        lbl_slider_desc = QHBoxLayout()
        lbl_slider_desc.addWidget(QLabel(tr("threshold_mild")))
        lbl_slider_desc.addStretch()
        lbl_slider_desc.addWidget(QLabel(tr("threshold_balanced")))
        lbl_slider_desc.addStretch()
        lbl_slider_desc.addWidget(QLabel(tr("threshold_strict")))
        layout.addLayout(lbl_slider_desc)

        # Listy VIP i słów kluczowych
        lists_layout = QHBoxLayout()

        # VIP
        vip_box = QVBoxLayout()
        vip_box.addWidget(QLabel(tr("step4_vip_label")))
        vip_input_layout = QHBoxLayout()
        self.txt_vip_input = QLineEdit()
        self.txt_vip_input.setPlaceholderText("szef@firma.pl")
        btn_add_vip = QPushButton(tr("add_btn"))
        btn_add_vip.clicked.connect(self._add_vip)
        vip_input_layout.addWidget(self.txt_vip_input)
        vip_input_layout.addWidget(btn_add_vip)
        vip_box.addLayout(vip_input_layout)

        self.list_vip = QListWidget()
        self.list_vip.setMaximumHeight(90)
        vip_box.addWidget(self.list_vip)
        btn_del_vip = QPushButton(tr("remove_btn"))
        btn_del_vip.clicked.connect(lambda: self._remove_selected(self.list_vip))
        vip_box.addWidget(btn_del_vip)
        lists_layout.addLayout(vip_box)

        # Słowa kluczowe
        kw_box = QVBoxLayout()
        kw_box.addWidget(QLabel(tr("step4_keywords_label")))
        kw_input_layout = QHBoxLayout()
        self.txt_kw_input = QLineEdit()
        self.txt_kw_input.setPlaceholderText("faktura, pilne")
        btn_add_kw = QPushButton(tr("add_btn"))
        btn_add_kw.clicked.connect(self._add_kw)
        kw_input_layout.addWidget(self.txt_kw_input)
        kw_input_layout.addWidget(btn_add_kw)
        kw_box.addLayout(kw_input_layout)

        self.list_kw = QListWidget()
        self.list_kw.setMaximumHeight(90)
        kw_box.addWidget(self.list_kw)
        btn_del_kw = QPushButton(tr("remove_btn"))
        btn_del_kw.clicked.connect(lambda: self._remove_selected(self.list_kw))
        kw_box.addWidget(btn_del_kw)
        lists_layout.addLayout(kw_box)

        layout.addLayout(lists_layout)

        # Okres podsumowania tematów (dni)
        layout.addWidget(QLabel(tr("step4_digest_days_label")))
        self.spin_digest_days = QSpinBox()
        self.spin_digest_days.setRange(1, 365)
        self.spin_digest_days.setValue(30)
        layout.addWidget(self.spin_digest_days)

    def _add_vip(self) -> None:
        text = self.txt_vip_input.text().strip()
        if text:
            self.list_vip.addItem(QListWidgetItem(text))
            self.txt_vip_input.clear()

    def _add_kw(self) -> None:
        text = self.txt_kw_input.text().strip()
        if text:
            for item in text.split(","):
                clean = item.strip()
                if clean:
                    self.list_kw.addItem(QListWidgetItem(clean))
            self.txt_kw_input.clear()

    def _remove_selected(self, widget: QListWidget) -> None:
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    def get_vip_senders(self) -> list[str]:
        return [self.list_vip.item(i).text() for i in range(self.list_vip.count())]

    def get_keywords(self) -> list[str]:
        return [self.list_kw.item(i).text() for i in range(self.list_kw.count())]

    def get_importance_threshold(self) -> int:
        return self.slider.value()

    def get_analysis_prompt(self) -> str:
        return self.txt_desc.toPlainText().strip()

    def get_digest_days(self) -> int:
        return self.spin_digest_days.value()


class VoicePage(QWizardPage):
    """Krok 5: Wybór interwału, trybu powiadomień i test głosu."""

    def __init__(self, speaker: Speaker | None = None) -> None:
        super().__init__()
        self.speaker = speaker or FakeSpeaker()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setTitle(tr("step5_title"))
        layout = QVBoxLayout(self)

        # Interwał
        layout.addWidget(QLabel(tr("step5_interval_label")))
        self.cb_interval = QComboBox()
        self.cb_interval.addItem(tr("minutes_5"), 5)
        self.cb_interval.addItem(tr("minutes_10"), 10)
        self.cb_interval.addItem(tr("minutes_15"), 15)
        self.cb_interval.addItem(tr("minutes_30"), 30)
        self.cb_interval.setCurrentIndex(1)  # 10 min
        layout.addWidget(self.cb_interval)
        layout.addSpacing(10)

        # Tryb powiadomień
        layout.addWidget(QLabel(tr("step5_mode_label")))
        self.rb_ask = QRadioButton(tr("mode_ask"))
        self.rb_beep = QRadioButton(tr("mode_beep"))
        self.rb_beep.setChecked(True)
        self.bg_mode = QButtonGroup(self)
        self.bg_mode.addButton(self.rb_beep)
        self.bg_mode.addButton(self.rb_ask)
        layout.addWidget(self.rb_beep)
        layout.addWidget(self.rb_ask)
        layout.addSpacing(15)

        # Test głosu
        self.btn_test_voice = QPushButton(tr("step5_test_voice_btn"))
        self.btn_test_voice.clicked.connect(self._test_voice)
        layout.addWidget(self.btn_test_voice)

        self.lbl_voice_status = QLabel("")
        self.lbl_voice_status.setWordWrap(True)
        layout.addWidget(self.lbl_voice_status)

        layout.addStretch()

    def _test_voice(self) -> None:
        lang = get_language()
        text = tr("step5_voice_sample_text")
        try:
            # Używamy faktycznego głośnika lub PiperSpeaker jeśli dostępny
            speaker = PiperSpeaker() if not isinstance(self.speaker, FakeSpeaker) else self.speaker
            speaker.speak(text, lang=lang)
            self.lbl_voice_status.setStyleSheet(f"color: {theme.c('ok')};")
            self.lbl_voice_status.setText(
                "Odtwarzanie próbki głosu..." if lang == "pl" else "Playing sample voice..."
            )
        except VoiceUnavailable as exc:
            self.lbl_voice_status.setStyleSheet(f"color: {theme.c('warn')};")
            self.lbl_voice_status.setText(str(exc))
        except Exception as exc:
            self.lbl_voice_status.setStyleSheet(f"color: {theme.c('error')};")
            self.lbl_voice_status.setText(str(exc))

    def get_interval_minutes(self) -> int:
        return self.cb_interval.currentData() or 10

    def get_notify_mode(self) -> str:
        return "ask" if self.rb_ask.isChecked() else "beep"


class FinishPage(QWizardPage):
    """Krok 6: Podsumowanie i zakończenie konfiguracji."""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle(tr("step6_title"))
        layout = QVBoxLayout(self)

        desc = QLabel(tr("step6_desc"))
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch()


class SetupWizard(QWizard):
    """Główny kreator pierwszego uruchomienia MailVoice."""

    def __init__(
        self,
        secret_store: SecretStore,
        speaker: Speaker | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.secret_store = secret_store
        self.speaker = speaker or FakeSpeaker()
        self.setWindowTitle(tr("wizard_title"))
        self.resize(680, 520)

        # Strony
        self.page_welcome = WelcomePage(self._retranslate_ui)
        self.page_account = AccountPage(self.secret_store)
        self.page_ollama = OllamaPage()
        self.page_importance = ImportancePage()
        self.page_voice = VoicePage(self.speaker)
        self.page_finish = FinishPage()

        self.addPage(self.page_welcome)
        self.addPage(self.page_account)
        self.addPage(self.page_ollama)
        self.addPage(self.page_importance)
        self.addPage(self.page_voice)
        self.addPage(self.page_finish)

        self._update_button_texts()

    def _retranslate_ui(self, lang: str) -> None:
        self.setWindowTitle(tr("wizard_title"))
        self._update_button_texts()

    def _update_button_texts(self) -> None:
        self.setButtonText(QWizard.WizardButton.NextButton, tr("btn_next"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("btn_back"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("btn_finish"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("btn_cancel"))

    def get_app_config(self) -> AppConfig:
        """Kompiluje pełny obiekt AppConfig na podstawie formularzy kreatora."""
        account = self.page_account.get_account_config()
        ollama = self.page_ollama.get_ollama_config()
        return AppConfig(
            accounts=[account],
            analysis_prompt=self.page_importance.get_analysis_prompt(),
            vip_senders=self.page_importance.get_vip_senders(),
            keywords=self.page_importance.get_keywords(),
            blocked_senders=[],
            interval_minutes=self.page_voice.get_interval_minutes(),
            notify_mode=self.page_voice.get_notify_mode(),
            beep_repeat_minutes=5,
            ask_retry_minutes=15,
            importance_threshold=self.page_importance.get_importance_threshold(),
            backlog_days=30,
            digest_days=self.page_importance.get_digest_days(),
            language=get_language(),
            ollama=ollama,
        )
