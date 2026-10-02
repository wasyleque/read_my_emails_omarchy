"""Okno ustawień aplikacji MailVoice."""

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig, save_config
from mailvoice.core.providers import get_provider_by_id, get_providers
from mailvoice.core.secrets import SecretStore
from mailvoice.ui.i18n import get_language, tr
from mailvoice.voice.tts import FakeSpeaker, PiperSpeaker, Speaker, VoiceUnavailable


class SettingsDialog(QDialog):
    """Okno dialogowe konfiguracji aplikacji MailVoice."""

    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        secret_store: SecretStore,
        speaker: Speaker | None = None,
        on_config_saved: Callable[[AppConfig], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.secret_store = secret_store
        self.speaker = speaker or FakeSpeaker()
        self.on_config_saved = on_config_saved

        self.setWindowTitle(tr("settings_title"))
        self.resize(650, 480)
        self._init_ui()
        self._load_values()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)

        # Zakładka 1: Konto pocztowe
        self.tab_account = QWidget()
        self._init_account_tab()
        self.tabs.addTab(self.tab_account, tr("tab_account"))

        # Zakładka 2: Ocenianie ważności
        self.tab_analysis = QWidget()
        self._init_analysis_tab()
        self.tabs.addTab(self.tab_analysis, tr("tab_analysis"))

        # Zakładka 3: Głos i powiadomienia
        self.tab_voice = QWidget()
        self._init_voice_tab()
        self.tabs.addTab(self.tab_voice, tr("tab_notifications"))

        # Zakładka 4: Ollama
        self.tab_ollama = QWidget()
        self._init_ollama_tab()
        self.tabs.addTab(self.tab_ollama, tr("tab_ollama"))

        layout.addWidget(self.tabs)

        # Dolne przyciski
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton(tr("btn_save"))
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton(tr("btn_close"))
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _init_account_tab(self) -> None:
        layout = QVBoxLayout(self.tab_account)
        form = QFormLayout()

        self.cb_provider = QComboBox()
        self.providers = get_providers()
        for p in self.providers:
            self.cb_provider.addItem(p.display_name, p.provider_id)
        self.cb_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(tr("step2_provider"), self.cb_provider)

        self.txt_email = QLineEdit()
        form.addRow(tr("step2_email"), self.txt_email)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("•••••••• (pozostaw puste, aby nie zmieniać)")
        form.addRow(tr("step2_password"), self.txt_password)

        layout.addLayout(form)

        self.lbl_help = QLabel()
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.lbl_help)

        # Sekcja zaawansowana
        self.acc_advanced = QGroupBox(tr("step2_advanced"))
        self.acc_advanced.setCheckable(True)
        self.acc_advanced.setChecked(False)
        adv_form = QFormLayout(self.acc_advanced)

        self.txt_host = QLineEdit()
        adv_form.addRow(tr("step2_host"), self.txt_host)

        self.txt_port = QLineEdit("993")
        adv_form.addRow(tr("step2_port"), self.txt_port)

        self.chk_ssl = QCheckBox("SSL / TLS")
        self.chk_ssl.setChecked(True)
        adv_form.addRow("", self.chk_ssl)

        layout.addWidget(self.acc_advanced)
        layout.addStretch()

    def _init_analysis_tab(self) -> None:
        layout = QVBoxLayout(self.tab_analysis)

        # Szablony
        tmpl_layout = QHBoxLayout()
        tmpl_layout.addWidget(QLabel(tr("step4_templates_label")))
        btn_work = QPushButton(tr("template_work"))
        btn_home = QPushButton(tr("template_home"))
        btn_biz = QPushButton(tr("template_business"))
        btn_work.clicked.connect(lambda: self.txt_desc.setText(tr("template_work_text")))
        btn_home.clicked.connect(lambda: self.txt_desc.setText(tr("template_home_text")))
        btn_biz.clicked.connect(lambda: self.txt_desc.setText(tr("template_business_text")))
        tmpl_layout.addWidget(btn_work)
        tmpl_layout.addWidget(btn_home)
        tmpl_layout.addWidget(btn_biz)
        tmpl_layout.addStretch()
        layout.addLayout(tmpl_layout)

        layout.addWidget(QLabel(tr("step4_desc_label")))
        self.txt_desc = QTextEdit()
        self.txt_desc.setMaximumHeight(70)
        layout.addWidget(self.txt_desc)

        layout.addWidget(QLabel(tr("step4_threshold_label")))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 10)
        layout.addWidget(self.slider)

        lists_layout = QHBoxLayout()

        # VIP
        vip_box = QVBoxLayout()
        vip_box.addWidget(QLabel(tr("step4_vip_label")))
        vip_in = QHBoxLayout()
        self.txt_vip = QLineEdit()
        btn_add_vip = QPushButton(tr("add_btn"))
        btn_add_vip.clicked.connect(self._add_vip)
        vip_in.addWidget(self.txt_vip)
        vip_in.addWidget(btn_add_vip)
        vip_box.addLayout(vip_in)

        self.list_vip = QListWidget()
        self.list_vip.setMaximumHeight(80)
        vip_box.addWidget(self.list_vip)
        btn_del_vip = QPushButton(tr("remove_btn"))
        btn_del_vip.clicked.connect(lambda: self._remove_selected(self.list_vip))
        vip_box.addWidget(btn_del_vip)
        lists_layout.addLayout(vip_box)

        # Słowa
        kw_box = QVBoxLayout()
        kw_box.addWidget(QLabel(tr("step4_keywords_label")))
        kw_in = QHBoxLayout()
        self.txt_kw = QLineEdit()
        btn_add_kw = QPushButton(tr("add_btn"))
        btn_add_kw.clicked.connect(self._add_kw)
        kw_in.addWidget(self.txt_kw)
        kw_in.addWidget(btn_add_kw)
        kw_box.addLayout(kw_in)

        self.list_kw = QListWidget()
        self.list_kw.setMaximumHeight(80)
        kw_box.addWidget(self.list_kw)
        btn_del_kw = QPushButton(tr("remove_btn"))
        btn_del_kw.clicked.connect(lambda: self._remove_selected(self.list_kw))
        kw_box.addWidget(btn_del_kw)
        lists_layout.addLayout(kw_box)

        layout.addLayout(lists_layout)

        # Okres podsumowania tematów (dni)
        layout.addWidget(QLabel(tr("settings_digest_days_label")))
        self.spin_digest_days = QSpinBox()
        self.spin_digest_days.setRange(1, 365)
        self.spin_digest_days.setValue(self.config.digest_days)
        layout.addWidget(self.spin_digest_days)

    def _init_voice_tab(self) -> None:
        layout = QVBoxLayout(self.tab_voice)

        layout.addWidget(QLabel(tr("step5_interval_label")))
        self.cb_interval = QComboBox()
        self.cb_interval.addItem(tr("minutes_5"), 5)
        self.cb_interval.addItem(tr("minutes_10"), 10)
        self.cb_interval.addItem(tr("minutes_15"), 15)
        self.cb_interval.addItem(tr("minutes_30"), 30)
        layout.addWidget(self.cb_interval)
        layout.addSpacing(10)

        layout.addWidget(QLabel(tr("step5_mode_label")))
        self.rb_beep = QRadioButton(tr("mode_beep"))
        self.rb_ask = QRadioButton(tr("mode_ask"))
        self.bg_mode = QButtonGroup(self)
        self.bg_mode.addButton(self.rb_beep)
        self.bg_mode.addButton(self.rb_ask)
        layout.addWidget(self.rb_beep)
        layout.addWidget(self.rb_ask)
        layout.addSpacing(15)

        self.btn_test_voice = QPushButton(tr("step5_test_voice_btn"))
        self.btn_test_voice.clicked.connect(self._test_voice)
        layout.addWidget(self.btn_test_voice)

        self.lbl_voice_status = QLabel("")
        layout.addWidget(self.lbl_voice_status)
        layout.addStretch()

    def _init_ollama_tab(self) -> None:
        layout = QVBoxLayout(self.tab_ollama)
        form = QFormLayout()

        self.txt_model = QLineEdit()
        form.addRow(tr("step3_model_label"), self.txt_model)

        self.adv_ollama = QGroupBox(tr("step3_advanced_url"))
        self.adv_ollama.setCheckable(True)
        self.adv_ollama.setChecked(False)
        adv_form = QFormLayout(self.adv_ollama)
        self.txt_local_url = QLineEdit()
        self.txt_lan_url = QLineEdit()
        adv_form.addRow("Local URL:", self.txt_local_url)
        adv_form.addRow("LAN URL:", self.txt_lan_url)

        layout.addLayout(form)
        layout.addWidget(self.adv_ollama)
        layout.addStretch()

    def _load_values(self) -> None:
        # Konto
        if self.config.accounts:
            acc = self.config.accounts[0]
            self.txt_email.setText(acc.username)
            self.txt_host.setText(acc.host)
            self.txt_port.setText(str(acc.port))
            self.chk_ssl.setChecked(acc.use_ssl)

        # Reguły
        self.txt_desc.setText(self.config.analysis_prompt)
        self.slider.setValue(self.config.importance_threshold)
        for vip in self.config.vip_senders:
            self.list_vip.addItem(vip)
        for kw in self.config.keywords:
            self.list_kw.addItem(kw)
        self.spin_digest_days.setValue(self.config.digest_days)

        # Głos
        idx = self.cb_interval.findData(self.config.interval_minutes)
        if idx >= 0:
            self.cb_interval.setCurrentIndex(idx)
        if self.config.notify_mode == "ask":
            self.rb_ask.setChecked(True)
        else:
            self.rb_beep.setChecked(True)

        # Ollama
        self.txt_model.setText(self.config.ollama.model)
        self.txt_local_url.setText(self.config.ollama.local_url)
        self.txt_lan_url.setText(self.config.ollama.lan_url)

    def _on_provider_changed(self, index: int) -> None:
        p_id = self.cb_provider.currentData()
        provider = get_provider_by_id(p_id)
        if provider.host:
            self.txt_host.setText(provider.host)
            self.txt_port.setText(str(provider.port))
            self.chk_ssl.setChecked(provider.use_ssl)
        lang = get_language()
        help_text = provider.help_text_pl if lang == "pl" else provider.help_text_en
        self.lbl_help.setText(help_text)

    def _add_vip(self) -> None:
        text = self.txt_vip.text().strip()
        if text:
            self.list_vip.addItem(QListWidgetItem(text))
            self.txt_vip.clear()

    def _add_kw(self) -> None:
        text = self.txt_kw.text().strip()
        if text:
            for item in text.split(","):
                clean = item.strip()
                if clean:
                    self.list_kw.addItem(QListWidgetItem(clean))
            self.txt_kw.clear()

    def _remove_selected(self, widget: QListWidget) -> None:
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    def _test_voice(self) -> None:
        lang = get_language()
        text = tr("step5_voice_sample_text")
        try:
            speaker = PiperSpeaker() if not isinstance(self.speaker, FakeSpeaker) else self.speaker
            speaker.speak(text, lang=lang)
            self.lbl_voice_status.setStyleSheet("color: green;")
            self.lbl_voice_status.setText(
                "Odtwarzanie próbki głosu..." if lang == "pl" else "Playing sample voice..."
            )
        except VoiceUnavailable as exc:
            self.lbl_voice_status.setStyleSheet("color: #b85d00;")
            self.lbl_voice_status.setText(str(exc))
        except Exception as exc:
            self.lbl_voice_status.setStyleSheet("color: red;")
            self.lbl_voice_status.setText(str(exc))

    def _on_save(self) -> None:
        email = self.txt_email.text().strip()
        password = self.txt_password.text()
        if password and email:
            self.secret_store.set(email, password)

        host = self.txt_host.text().strip()
        try:
            port = int(self.txt_port.text().strip())
        except ValueError:
            port = 993

        accounts = []
        if email:
            p_id = self.cb_provider.currentData()
            provider = get_provider_by_id(p_id)
            accounts.append(
                AccountConfig(
                    name=email,
                    host=host or provider.host,
                    port=port,
                    username=email,
                    use_ssl=self.chk_ssl.isChecked(),
                    folders=["INBOX"],
                    sent_folder=provider.sent_folder,
                )
            )
        elif self.config.accounts:
            accounts = self.config.accounts

        vip_senders = [self.list_vip.item(i).text() for i in range(self.list_vip.count())]
        keywords = [self.list_kw.item(i).text() for i in range(self.list_kw.count())]

        ollama_cfg = OllamaConfig(
            lan_url=self.txt_lan_url.text().strip() or self.config.ollama.lan_url,
            local_url=self.txt_local_url.text().strip() or self.config.ollama.local_url,
            model=self.txt_model.text().strip() or self.config.ollama.model,
            polish_model=self.config.ollama.polish_model,
            prefer=self.config.ollama.prefer,
        )

        new_config = AppConfig(
            accounts=accounts,
            analysis_prompt=self.txt_desc.toPlainText().strip(),
            vip_senders=vip_senders,
            keywords=keywords,
            blocked_senders=self.config.blocked_senders,
            interval_minutes=self.cb_interval.currentData() or 10,
            notify_mode="ask" if self.rb_ask.isChecked() else "beep",
            beep_repeat_minutes=self.config.beep_repeat_minutes,
            ask_retry_minutes=self.config.ask_retry_minutes,
            importance_threshold=self.slider.value(),
            backlog_days=self.config.backlog_days,
            digest_days=self.spin_digest_days.value(),
            language=get_language(),
            ollama=ollama_cfg,
        )

        try:
            save_config(new_config, self.config_path)
            if self.on_config_saved:
                self.on_config_saved(new_config)
            QMessageBox.information(self, "MailVoice", tr("save_success"))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "MailVoice", f"Błąd zapisu: {exc}")
