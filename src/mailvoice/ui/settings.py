from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import platformdirs
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig, ServerConfig, save_config
from mailvoice.core.devices import DeviceManager
from mailvoice.core.ignore import IgnoreRule
from mailvoice.core.ollama_models import (
    CheckResult,
    Detection,
    check_model,
    describe_selection,
    detect_models,
    get_available_models,
    suggest_models,
)
from mailvoice.core.providers import get_provider_by_id, get_providers
from mailvoice.core.secrets import SecretStore
from mailvoice.core.tls import detect_lan_ip
from mailvoice.ui import theme
from mailvoice.ui.i18n import get_language, tr
from mailvoice.ui.pairing_dialog import PairingDialog
from mailvoice.ui.wizard import ImapTestWorker
from mailvoice.voice.tts import FakeSpeaker, PiperSpeaker, Speaker, VoiceUnavailable


@dataclass
class AccountDraft:
    """Robocza wersja konta w oknie dialogowym ustawień."""

    original_name: str | None
    name: str
    provider_id: str
    host: str
    port: int
    username: str
    use_ssl: bool
    sent_folder: str
    folders: list[str] = field(default_factory=lambda: ["INBOX"])
    new_password: str | None = None
    has_stored_password: bool = False


def detect_provider_id(acc: AccountConfig) -> str:
    """Wykrywa identyfikator dostawcy poczty na podstawie konfiguracji konta."""
    for p in get_providers():
        if p.provider_id != "other" and p.host.lower() == acc.host.lower():
            return p.provider_id
    domain = acc.username.split("@")[-1].lower() if "@" in acc.username else ""
    if "gmail" in domain:
        return "gmail"
    if "outlook" in domain or "hotmail" in domain:
        return "outlook"
    if "wp.pl" in domain:
        return "wp"
    if "o2.pl" in domain:
        return "o2"
    if "onet.pl" in domain:
        return "onet"
    if "interia" in domain:
        return "interia"
    return "other"


class OllamaDetectWorker(QThread):
    """Wątek wykrywania serwera Ollama i pobierania listy modeli."""

    finished_detection = Signal(object)

    def __init__(
        self,
        local_url: str,
        lan_url: str,
        fetch_fn: Callable[[str], list[str]] | None = None,
    ) -> None:
        super().__init__()
        self.local_url = local_url
        self.lan_url = lan_url
        self.fetch_fn = fetch_fn

    def run(self) -> None:
        detection = detect_models(self.local_url, self.lan_url, fetch=self.fetch_fn)
        self.finished_detection.emit(detection)


class OllamaCheckWorker(QThread):
    """Wątek wysyłający zapytanie testowe do wybranego modelu Ollama."""

    finished_check = Signal(object)

    def __init__(
        self,
        cfg: OllamaConfig,
        model: str,
        client_factory: Callable[[OllamaConfig], OllamaClient] | None = None,
        lang: str = "pl",
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.model = model
        self.client_factory = client_factory
        self.lang = lang

    def run(self) -> None:
        result = check_model(
            self.cfg,
            self.model,
            client_factory=self.client_factory,
            lang=self.lang,
        )
        self.finished_check.emit(result)


class SettingsDialog(QDialog):
    """Okno dialogowe konfiguracji aplikacji MailVoice."""

    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        secret_store: SecretStore,
        speaker: Speaker | None = None,
        on_config_saved: Callable[[AppConfig], None] | None = None,
        device_manager: DeviceManager | None = None,
        data_dir: Path | None = None,
        server_status: Callable[[], tuple[bool, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.secret_store = secret_store
        self.speaker = speaker or FakeSpeaker()
        self.on_config_saved = on_config_saved
        self.server_status = server_status
        self.data_dir = data_dir or (
            self.config_path.parent
            if self.config_path
            else Path(platformdirs.user_data_dir("mailvoice"))
        )
        self.device_manager = device_manager or DeviceManager(self.data_dir / "mailvoice.db")
        self.worker: ImapTestWorker | None = None
        self.account_drafts: list[AccountDraft] = []
        self.deleted_account_names: list[str] = []
        self._current_account_index: int = -1
        self._is_updating_form: bool = False
        self.ollama_detect_worker: OllamaDetectWorker | None = None
        self.ollama_check_worker: OllamaCheckWorker | None = None
        self.ollama_detection: Detection | None = None
        self._ollama_fetch_fn: Callable[[str], list[str]] | None = None
        self._ollama_client_factory: Callable[[OllamaConfig], OllamaClient] | None = None
        self._ollama_detected_once: bool = False

        self.setWindowTitle(tr("settings_title"))
        self.resize(840, 540)
        self._init_ui()
        self._load_values()

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        """Zakładka w obszarze przewijania: przy małej rozdzielczości formularz się przewija."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(page)
        return area

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)

        # Zakładka 1: Konto pocztowe
        self.tab_account = QWidget()
        self._init_account_tab()
        self.tabs.addTab(self._scrollable(self.tab_account), tr("tab_account"))

        # Zakładki 2-4: Ocenianie ważności podzielone na trzy mniejsze strony
        self.tab_analysis = QWidget()
        self.tab_people = QWidget()
        self.tab_rules = QWidget()
        self._init_analysis_tab()
        self.tabs.addTab(self._scrollable(self.tab_analysis), tr("tab_importance"))
        self.tabs.addTab(self._scrollable(self.tab_people), tr("tab_people"))
        self.tabs.addTab(self._scrollable(self.tab_rules), tr("tab_rules"))

        # Zakładka 5: Głos i powiadomienia
        self.tab_voice = QWidget()
        self._init_voice_tab()
        self.tabs.addTab(self._scrollable(self.tab_voice), tr("tab_notifications"))

        # Zakładka 6: Ollama
        self.tab_ollama = QWidget()
        self._init_ollama_tab()
        self._ollama_page = self._scrollable(self.tab_ollama)
        self.tabs.addTab(self._ollama_page, tr("tab_ollama"))

        # Zakładka 7: Telefon (Android)
        self.tab_mobile = QWidget()
        self._init_mobile_tab()
        self.tabs.addTab(self._scrollable(self.tab_mobile), tr("tab_mobile"))

        self.tabs.currentChanged.connect(self._on_tab_changed)

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
        main_layout = QHBoxLayout(self.tab_account)

        # Lewa strona: lista kont i przyciski akcji
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        lbl_list = QLabel(tr("accounts_list_title"))
        lbl_list.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(lbl_list)

        self.list_accounts = QListWidget()
        self.list_accounts.currentRowChanged.connect(self._on_account_selection_changed)
        left_layout.addWidget(self.list_accounts)

        btn_row = QHBoxLayout()
        self.btn_add_account = QPushButton(tr("btn_add_account"))
        self.btn_add_account.clicked.connect(self._on_add_account)
        btn_row.addWidget(self.btn_add_account)

        self.btn_remove_account = QPushButton(tr("btn_remove_account"))
        self.btn_remove_account.clicked.connect(self._on_remove_account)
        btn_row.addWidget(self.btn_remove_account)
        left_layout.addLayout(btn_row)

        left_widget.setFixedWidth(300)
        main_layout.addWidget(left_widget)

        # Prawa strona: formularz edycji konta
        self.account_details_widget = QWidget()
        right_layout = QVBoxLayout(self.account_details_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)

        lbl_details = QLabel(tr("account_details_title"))
        lbl_details.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(lbl_details)

        form = QFormLayout()

        self.cb_provider = QComboBox()
        self.providers = get_providers()
        for p in self.providers:
            self.cb_provider.addItem(p.display_name, p.provider_id)
        self.cb_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(tr("step2_provider"), self.cb_provider)

        self.txt_email = QLineEdit()
        self.txt_email.textChanged.connect(self._on_account_input_changed)
        form.addRow(tr("step2_email"), self.txt_email)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("•••••••• (pozostaw puste, aby nie zmieniać)")
        self.txt_password.textChanged.connect(self._on_account_input_changed)
        form.addRow(tr("step2_password"), self.txt_password)

        self.lbl_password_status = QLabel("")
        self.lbl_password_status.setWordWrap(True)
        form.addRow("", self.lbl_password_status)

        right_layout.addLayout(form)

        self.lbl_help = QLabel()
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        right_layout.addWidget(self.lbl_help)

        # Sprawdzanie połączenia
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

        right_layout.addLayout(test_container)

        # Sekcja zaawansowana
        self.acc_advanced = QGroupBox(tr("step2_advanced"))
        self.acc_advanced.setCheckable(True)
        self.acc_advanced.setChecked(False)
        adv_form = QFormLayout(self.acc_advanced)

        self.txt_host = QLineEdit()
        self.txt_host.textChanged.connect(self._on_account_input_changed)
        adv_form.addRow(tr("step2_host"), self.txt_host)

        self.txt_port = QLineEdit("993")
        self.txt_port.textChanged.connect(self._on_account_input_changed)
        adv_form.addRow(tr("step2_port"), self.txt_port)

        self.chk_ssl = QCheckBox("SSL / TLS")
        self.chk_ssl.setChecked(True)
        self.chk_ssl.toggled.connect(self._on_account_input_changed)
        adv_form.addRow("", self.chk_ssl)

        self.txt_sent_folder = QLineEdit()
        self.txt_sent_folder.textChanged.connect(self._on_account_input_changed)
        adv_form.addRow(tr("step2_sent_folder"), self.txt_sent_folder)

        right_layout.addWidget(self.acc_advanced)
        right_layout.addStretch()

        main_layout.addWidget(self.account_details_widget)

    def _init_analysis_tab(self) -> None:
        layout = QVBoxLayout(self.tab_analysis)
        people_layout = QVBoxLayout(self.tab_people)
        rules_layout = QVBoxLayout(self.tab_rules)

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

        # VIP
        vip_box = QVBoxLayout()
        vip_box.addWidget(QLabel(tr("step4_vip_label")))
        lbl_vip_hint = QLabel(tr("vip_hint"))
        lbl_vip_hint.setWordWrap(True)
        lbl_vip_hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        vip_box.addWidget(lbl_vip_hint)
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
        people_layout.addLayout(vip_box)

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
        rules_layout.addLayout(kw_box)

        # Osoby, do których piszesz (automatycznie z folderu Wysłane)
        people_layout.addWidget(QLabel(tr("auto_vip_label")))
        self.cb_auto_vip = QComboBox()
        self.cb_auto_vip.addItem(tr("auto_vip_off"), "off")
        self.cb_auto_vip.addItem(tr("auto_vip_bonus"), "bonus")
        self.cb_auto_vip.addItem(tr("auto_vip_vip"), "vip")
        people_layout.addWidget(self.cb_auto_vip)
        lbl_auto_hint = QLabel(tr("auto_vip_hint"))
        lbl_auto_hint.setWordWrap(True)
        lbl_auto_hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        people_layout.addWidget(lbl_auto_hint)
        known_row = QHBoxLayout()
        self.lbl_known_people = QLabel("")
        known_row.addWidget(self.lbl_known_people)
        btn_show_known = QPushButton(tr("auto_vip_show"))
        btn_show_known.clicked.connect(self._show_known_people)
        known_row.addWidget(btn_show_known)
        known_row.addStretch()
        people_layout.addLayout(known_row)
        self._refresh_known_people()

        # Ignorowane maile: reguły (nadawca / domena / temat); stara lista blokowanych nadawców
        # jest tu pokazywana jako reguły „od: …” i po zapisie przechodzi do ignore_rules.
        rules_layout.addWidget(QLabel(tr("ignore_section_label")))
        ignore_in = QHBoxLayout()
        self.txt_ignore_sender = QLineEdit()
        self.txt_ignore_sender.setPlaceholderText(tr("ignore_sender_ph"))
        self.txt_ignore_subject = QLineEdit()
        self.txt_ignore_subject.setPlaceholderText(tr("ignore_subject_ph"))
        btn_add_ignore = QPushButton(tr("add_btn"))
        btn_add_ignore.clicked.connect(self._add_ignore_rule)
        ignore_in.addWidget(self.txt_ignore_sender)
        ignore_in.addWidget(self.txt_ignore_subject)
        ignore_in.addWidget(btn_add_ignore)
        rules_layout.addLayout(ignore_in)
        self.list_ignore = QListWidget()
        self.list_ignore.setMaximumHeight(90)
        rules_layout.addWidget(self.list_ignore)
        btn_del_ignore = QPushButton(tr("remove_btn"))
        btn_del_ignore.clicked.connect(lambda: self._remove_selected(self.list_ignore))
        rules_layout.addWidget(btn_del_ignore)
        lbl_ignore_hint = QLabel(tr("ignore_hint"))
        lbl_ignore_hint.setWordWrap(True)
        lbl_ignore_hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        rules_layout.addWidget(lbl_ignore_hint)

        # Okres podsumowania tematów (dni)
        layout.addWidget(QLabel(tr("settings_digest_days_label")))
        self.spin_digest_days = QSpinBox()
        self.spin_digest_days.setRange(1, 365)
        self.spin_digest_days.setValue(self.config.digest_days)
        layout.addWidget(self.spin_digest_days)
        layout.addStretch()
        people_layout.addStretch()
        rules_layout.addStretch()

    def _add_ignore_rule(self) -> None:
        rule = IgnoreRule(
            sender=self.txt_ignore_sender.text().strip(),
            subject=self.txt_ignore_subject.text().strip(),
        )
        if not rule.is_valid():
            return
        self._append_ignore_item(rule)
        self.txt_ignore_sender.clear()
        self.txt_ignore_subject.clear()

    def _append_ignore_item(self, rule: IgnoreRule) -> None:
        for i in range(self.list_ignore.count()):
            if self.list_ignore.item(i).data(Qt.ItemDataRole.UserRole) == rule:
                return
        item = QListWidgetItem(rule.describe())
        item.setData(Qt.ItemDataRole.UserRole, rule)
        self.list_ignore.addItem(item)

    def _collect_ignore_rules(self) -> list[IgnoreRule]:
        rules = []
        for i in range(self.list_ignore.count()):
            rule = self.list_ignore.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(rule, IgnoreRule) and rule not in rules:
                rules.append(rule)
        return rules

    def _known_people(self) -> tuple[frozenset[str], frozenset[str]]:
        """Adresy i domeny firmowe z Twoich wysłanych maili (tylko odczyt lokalnej bazy)."""
        from mailvoice.core.store import Store

        try:
            store = Store(self.data_dir / "mailvoice.db")
            try:
                mine = {a.username.lower() for a in self.config.accounts if a.username}
                return store.get_correspondents(exclude=mine)
            finally:
                store.close()
        except Exception:  # noqa: BLE001 — brak bazy/wysłanych nie może psuć okna ustawień
            return frozenset(), frozenset()

    def _refresh_known_people(self) -> None:
        addresses, domains = self._known_people()
        self.lbl_known_people.setText(
            tr("auto_vip_count", addresses=len(addresses), domains=len(domains))
        )

    def _show_known_people(self) -> None:
        addresses, domains = self._known_people()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("MailVoice")
        box.setText(tr("auto_vip_count", addresses=len(addresses), domains=len(domains)))
        listing = "\n".join(sorted(addresses)[:500])
        box.setDetailedText(listing or "-")
        box.exec()

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
        layout.addSpacing(10)

        layout.addWidget(QLabel(tr("voice_output_label")))
        self.cb_voice_output = QComboBox()
        self.cb_voice_output.addItem(tr("voice_output_auto"), "auto")
        self.cb_voice_output.addItem(tr("voice_output_computer"), "computer")
        self.cb_voice_output.addItem(tr("voice_output_phone"), "phone")
        self.cb_voice_output.addItem(tr("voice_output_both"), "both")
        layout.addWidget(self.cb_voice_output)
        lbl_out_hint = QLabel(tr("voice_output_hint"))
        lbl_out_hint.setWordWrap(True)
        lbl_out_hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        layout.addWidget(lbl_out_hint)
        layout.addSpacing(15)

        self.btn_test_voice = QPushButton(tr("step5_test_voice_btn"))
        self.btn_test_voice.clicked.connect(self._test_voice)
        layout.addWidget(self.btn_test_voice)

        self.lbl_voice_status = QLabel("")
        layout.addWidget(self.lbl_voice_status)
        layout.addStretch()

    def _on_tab_changed(self, index: int) -> None:
        # Zakładka 4 (index 3) to Model AI (Ollama)
        if self.tabs.widget(index) is self._ollama_page and not self._ollama_detected_once:
            self._on_detect_models()

    def _init_ollama_tab(self) -> None:
        layout = QVBoxLayout(self.tab_ollama)

        # 1. Pasek wykrywania modeli
        detect_layout = QHBoxLayout()
        self.btn_detect_models = QPushButton(tr("ollama_detect_btn"))
        self.btn_detect_models.clicked.connect(self._on_detect_models)
        detect_layout.addWidget(self.btn_detect_models)

        self.lbl_detect_status = QLabel("")
        self.lbl_detect_status.setWordWrap(True)
        detect_layout.addWidget(self.lbl_detect_status)
        detect_layout.addStretch()
        layout.addLayout(detect_layout)

        # Instrukcja instalacji / pomocy gdy brak serwera
        self.lbl_ollama_guide = QLabel(tr("ollama_install_guide"))
        self.lbl_ollama_guide.setWordWrap(True)
        self.lbl_ollama_guide.setStyleSheet(
            f"color: {theme.c('text')}; background: {theme.c('guide_bg')}; "
            "padding: 8px; border-radius: 4px;"
        )
        self.lbl_ollama_guide.setVisible(False)
        layout.addWidget(self.lbl_ollama_guide)

        # 2. Formularz wyboru modeli
        form = QFormLayout()

        # Model ogólny
        self.cb_model = QComboBox()
        self.cb_model.currentIndexChanged.connect(self._on_model_selection_changed)
        form.addRow(tr("ollama_general_model_label"), self.cb_model)

        # Ostrzeżenie o braku modelu
        self.lbl_model_warning = QLabel("")
        self.lbl_model_warning.setWordWrap(True)
        self.lbl_model_warning.setStyleSheet(f"color: {theme.c('warn')}; font-size: 11px;")
        self.lbl_model_warning.setVisible(False)
        form.addRow("", self.lbl_model_warning)

        # Model do języka polskiego
        self.cb_polish_model = QComboBox()
        form.addRow(tr("ollama_polish_model_label"), self.cb_polish_model)

        # Checkbox "Pokaż wszystkie modele"
        self.chk_all_models = QCheckBox(tr("ollama_show_all_models"))
        self.chk_all_models.setChecked(False)
        self.chk_all_models.toggled.connect(self._repopulate_model_combos)
        form.addRow("", self.chk_all_models)

        # Informacja o wykluczeniu modeli chmurowych
        self.lbl_cloud_hint = QLabel(tr("ollama_cloud_excluded_hint"))
        self.lbl_cloud_hint.setWordWrap(True)
        self.lbl_cloud_hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        form.addRow("", self.lbl_cloud_hint)

        layout.addLayout(form)

        # 3. Test modelu
        check_layout = QHBoxLayout()
        self.btn_check_model = QPushButton(tr("ollama_check_btn"))
        self.btn_check_model.clicked.connect(self._on_check_model)
        check_layout.addWidget(self.btn_check_model)

        self.lbl_check_result = QLabel("")
        self.lbl_check_result.setWordWrap(True)
        check_layout.addWidget(self.lbl_check_result)
        check_layout.addStretch()
        layout.addLayout(check_layout)

        # 4. Sekcja zaawansowana (URL-e)
        self.adv_ollama = QGroupBox(tr("step3_advanced_url"))
        self.adv_ollama.setCheckable(True)
        self.adv_ollama.setChecked(False)
        adv_form = QFormLayout(self.adv_ollama)

        self.txt_local_url = QLineEdit()
        self.txt_lan_url = QLineEdit()
        adv_form.addRow("Local URL:", self.txt_local_url)
        adv_form.addRow("LAN URL:", self.txt_lan_url)

        layout.addWidget(self.adv_ollama)
        layout.addStretch()

    def _init_mobile_tab(self) -> None:
        layout = QVBoxLayout(self.tab_mobile)
        layout.setSpacing(12)

        # 1. Przełącznik włączenia serwera
        self.cb_server_enabled = QCheckBox(tr("mobile_enable_label"))
        self.cb_server_enabled.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.cb_server_enabled.toggled.connect(self._on_server_enabled_toggled)
        layout.addWidget(self.cb_server_enabled)

        # 2. Ostrzeżenie po ludzku
        lbl_warning = QLabel(tr("mobile_warning"))
        lbl_warning.setWordWrap(True)
        lbl_warning.setStyleSheet(
            f"color: {theme.c('muted')}; font-style: italic; font-size: 11px;"
        )
        layout.addWidget(lbl_warning)

        # 3. Status serwera
        self.lbl_server_status = QLabel("")
        self.lbl_server_status.setWordWrap(True)
        layout.addWidget(self.lbl_server_status)

        # 4. Przycisk parowania nowego telefonu
        pair_row = QHBoxLayout()
        self.btn_pair = QPushButton(tr("btn_pair_device"))
        self.btn_pair.clicked.connect(self._on_pair_device)
        pair_row.addWidget(self.btn_pair)
        pair_row.addStretch()
        layout.addLayout(pair_row)

        layout.addSpacing(10)

        # 5. Lista sparowanych urządzeń
        lbl_devices = QLabel(tr("paired_devices_title"))
        lbl_devices.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_devices)

        self.list_devices = QListWidget()
        self.list_devices.currentRowChanged.connect(self._on_device_selection_changed)
        layout.addWidget(self.list_devices)

        # 6. Przycisk Odłącz urządzenie
        btn_dev_row = QHBoxLayout()
        self.btn_revoke_device = QPushButton(tr("btn_revoke_device"))
        self.btn_revoke_device.clicked.connect(self._on_revoke_device)
        self.btn_revoke_device.setEnabled(False)
        btn_dev_row.addWidget(self.btn_revoke_device)
        btn_dev_row.addStretch()
        layout.addLayout(btn_dev_row)

        layout.addStretch()

    def _on_server_enabled_toggled(self, enabled: bool) -> None:
        self._update_server_status_ui(enabled)

    def _update_server_status_ui(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = self.cb_server_enabled.isChecked()

        lan_ip = (
            self.config.server.bind
            if (self.config.server.bind and self.config.server.bind != "0.0.0.0")
            else detect_lan_ip()
        )

        if enabled:
            if lan_ip:
                url = f"https://{lan_ip}:{self.config.server.port}"
                self.lbl_server_status.setText(tr("mobile_status_listening", url=url))
                self.lbl_server_status.setStyleSheet(f"color: {theme.c('ok')}; font-weight: bold;")
                self.btn_pair.setEnabled(True)
            else:
                self.lbl_server_status.setText(tr("mobile_status_no_lan"))
                self.lbl_server_status.setStyleSheet(
                    f"color: {theme.c('warn')}; font-weight: bold;"
                )
                self.btn_pair.setEnabled(False)
        else:
            self.lbl_server_status.setText(tr("mobile_status_disabled"))
            self.lbl_server_status.setStyleSheet(f"color: {theme.c('muted')};")
            self.btn_pair.setEnabled(False)

    def _refresh_paired_devices(self) -> None:
        self.list_devices.clear()
        devices = self.device_manager.list_devices(include_revoked=False)
        for dev in devices:
            created = dev.created_at[:10] if dev.created_at else ""
            seen = dev.last_seen[:16].replace("T", " ") if dev.last_seen else tr("status_never")
            item_text = f"📱 {dev.name} (dodano: {created}, aktywność: {seen})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, dev)
            self.list_devices.addItem(item)
        if not devices:
            item = QListWidgetItem(tr("no_paired_devices"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.list_devices.addItem(item)
        self.btn_revoke_device.setEnabled(False)

    def _on_device_selection_changed(self, row: int) -> None:
        item = self.list_devices.item(row)
        dev = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.btn_revoke_device.setEnabled(dev is not None)

    def _on_pair_device(self) -> None:
        # Kod QR bez działającego serwera to pułapka: telefon zeskanuje go i trafi w pustkę.
        if not self.cb_server_enabled.isChecked():
            QMessageBox.information(self, "MailVoice", tr("mobile_pair_need_enable"))
            return
        if self.server_status is not None:
            running, detail = self.server_status()
            if not running:
                QMessageBox.warning(
                    self, "MailVoice", tr("mobile_pair_server_down", detail=detail or "-")
                )
                return
        dlg = PairingDialog(
            device_manager=self.device_manager,
            port=self.config.server.port,
            data_dir=self.data_dir,
            bind_host=self.config.server.bind,
            parent=self,
        )
        dlg.exec()
        self._refresh_paired_devices()

    def _on_revoke_device(self) -> None:
        row = self.list_devices.currentRow()
        item = self.list_devices.item(row)
        if not item:
            return
        dev = item.data(Qt.ItemDataRole.UserRole)
        if not dev:
            return

        ans = QMessageBox.question(
            self,
            "MailVoice",
            tr("revoke_device_confirm", name=dev.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.device_manager.revoke_device(dev.id)
            self._refresh_paired_devices()

    def _load_values(self) -> None:
        # Konta
        self.account_drafts.clear()
        self.deleted_account_names.clear()
        self.list_accounts.clear()

        for acc in self.config.accounts:
            p_id = detect_provider_id(acc)
            has_secret = False
            try:
                stored = self.secret_store.get(acc.name)
                has_secret = bool(stored)
            except Exception:
                has_secret = False

            draft = AccountDraft(
                original_name=acc.name,
                name=acc.name,
                provider_id=p_id,
                host=acc.host,
                port=acc.port,
                username=acc.username,
                use_ssl=acc.use_ssl,
                sent_folder=acc.sent_folder,
                folders=list(acc.folders) if acc.folders else ["INBOX"],
                new_password=None,
                has_stored_password=has_secret,
            )
            self.account_drafts.append(draft)
            item = QListWidgetItem()
            self.list_accounts.addItem(item)
            self._update_list_item(len(self.account_drafts) - 1)

        if self.account_drafts:
            self.list_accounts.setCurrentRow(0)
        else:
            self._current_account_index = -1
            self._clear_form()
            self.account_details_widget.setEnabled(False)
            self.btn_remove_account.setEnabled(False)

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
        self.cb_auto_vip.setCurrentIndex(max(self.cb_auto_vip.findData(self.config.auto_vip), 0))
        self.list_ignore.clear()
        for blocked in self.config.blocked_senders:
            self._append_ignore_item(IgnoreRule(sender=blocked))
        for rule in self.config.ignore_rules:
            self._append_ignore_item(rule)
        idx = self.cb_voice_output.findData(self.config.voice_output)
        self.cb_voice_output.setCurrentIndex(max(idx, 0))
        if self.config.notify_mode == "ask":
            self.rb_ask.setChecked(True)
        else:
            self.rb_beep.setChecked(True)

        # Ollama
        self.txt_local_url.setText(self.config.ollama.local_url)
        self.txt_lan_url.setText(self.config.ollama.lan_url)
        self._repopulate_model_combos()

        # Telefon (Android)
        self.cb_server_enabled.setChecked(self.config.server.enabled)
        self._update_server_status_ui()
        self._refresh_paired_devices()

    def _load_draft_to_form(self, draft: AccountDraft) -> None:
        self._is_updating_form = True
        try:
            idx = self.cb_provider.findData(draft.provider_id)
            if idx >= 0:
                self.cb_provider.setCurrentIndex(idx)
            else:
                self.cb_provider.setCurrentIndex(self.cb_provider.findData("other"))

            self.txt_email.setText(draft.username)
            self.txt_password.setText(draft.new_password or "")
            self.txt_host.setText(draft.host)
            self.txt_port.setText(str(draft.port))
            self.chk_ssl.setChecked(draft.use_ssl)
            self.txt_sent_folder.setText(draft.sent_folder)

            provider = get_provider_by_id(draft.provider_id)
            lang = get_language()
            help_text = provider.help_text_pl if lang == "pl" else provider.help_text_en
            self.lbl_help.setText(help_text)

            self.lbl_test_result.setText("")
            self.btn_details.setVisible(False)
            self.txt_details.setVisible(False)

            self._update_password_status_label(draft)
        finally:
            self._is_updating_form = False

    def _clear_form(self) -> None:
        self._is_updating_form = True
        try:
            self.txt_email.clear()
            self.txt_password.clear()
            self.txt_host.clear()
            self.txt_port.setText("993")
            self.chk_ssl.setChecked(True)
            self.txt_sent_folder.clear()
            self.lbl_help.setText("")
            self.lbl_test_result.setText("")
            self.lbl_password_status.setText("")
            self.btn_details.setVisible(False)
            self.txt_details.setVisible(False)
        finally:
            self._is_updating_form = False

    def _save_form_to_draft(self, index: int) -> None:
        if index < 0 or index >= len(self.account_drafts):
            return
        draft = self.account_drafts[index]
        email = self.txt_email.text().strip()
        draft.name = email
        draft.username = email
        p_id = self.cb_provider.currentData()
        if p_id:
            draft.provider_id = p_id
        draft.host = self.txt_host.text().strip()
        try:
            draft.port = int(self.txt_port.text().strip())
        except ValueError:
            draft.port = 993
        draft.use_ssl = self.chk_ssl.isChecked()
        draft.sent_folder = self.txt_sent_folder.text().strip()
        pwd = self.txt_password.text()
        if pwd:
            draft.new_password = pwd
        else:
            draft.new_password = None
        self._update_list_item(index)

    def _update_list_item(self, index: int) -> None:
        item = self.list_accounts.item(index)
        if not item or index >= len(self.account_drafts):
            return
        draft = self.account_drafts[index]
        display_name = draft.name.strip() if draft.name.strip() else tr("new_account_label")
        provider = get_provider_by_id(draft.provider_id)
        if draft.provider_id == "other":
            prov_name = "Własny IMAP" if get_language() == "pl" else "Custom IMAP"
        else:
            prov_name = provider.display_name.split(" (")[0].split(" /")[0]
        has_pwd = (draft.new_password is not None) or draft.has_stored_password
        status_text = tr("acc_status_pwd_saved") if has_pwd else tr("acc_status_no_pwd")
        item.setText(f"{display_name}\n{prov_name} • {status_text}")

    def _update_password_status_label(self, draft: AccountDraft) -> None:
        if draft.new_password:
            self.lbl_password_status.setStyleSheet(f"color: {theme.c('accent')}; font-size: 11px;")
            self.lbl_password_status.setText(
                "● Nowe hasło wprowadzone" if get_language() == "pl" else "● New password entered"
            )
        elif draft.has_stored_password:
            self.lbl_password_status.setStyleSheet(f"color: {theme.c('ok')}; font-size: 11px;")
            self.lbl_password_status.setText(
                "✓ Hasło zapisane w sejfie"
                if get_language() == "pl"
                else "✓ Password saved in vault"
            )
        else:
            self.lbl_password_status.setStyleSheet(f"color: {theme.c('warn')}; font-size: 11px;")
            self.lbl_password_status.setText(
                "⚠ Brak hasła (wprowadź hasło)"
                if get_language() == "pl"
                else "⚠ No password (enter password)"
            )

    def _on_account_selection_changed(self, new_row: int) -> None:
        if self._is_updating_form:
            return

        if 0 <= self._current_account_index < len(self.account_drafts):
            self._save_form_to_draft(self._current_account_index)

        self._current_account_index = new_row
        if 0 <= new_row < len(self.account_drafts):
            draft = self.account_drafts[new_row]
            self._load_draft_to_form(draft)
            self.account_details_widget.setEnabled(True)
            self.btn_remove_account.setEnabled(True)
        else:
            self._clear_form()
            self.account_details_widget.setEnabled(False)
            self.btn_remove_account.setEnabled(False)

    def _on_add_account(self) -> None:
        if 0 <= self._current_account_index < len(self.account_drafts):
            self._save_form_to_draft(self._current_account_index)

        default_provider = self.providers[0] if self.providers else get_provider_by_id("gmail")
        new_draft = AccountDraft(
            original_name=None,
            name="",
            provider_id=default_provider.provider_id,
            host=default_provider.host,
            port=default_provider.port,
            username="",
            use_ssl=default_provider.use_ssl,
            sent_folder=default_provider.sent_folder,
            folders=["INBOX"],
            new_password=None,
            has_stored_password=False,
        )
        self.account_drafts.append(new_draft)
        item = QListWidgetItem()
        self.list_accounts.addItem(item)
        new_row = len(self.account_drafts) - 1
        self._update_list_item(new_row)
        self.list_accounts.setCurrentRow(new_row)
        self.txt_email.setFocus()

    def _on_remove_account(self) -> None:
        row = self.list_accounts.currentRow()
        if row < 0 or row >= len(self.account_drafts):
            return

        draft = self.account_drafts[row]
        acc_name = draft.name or draft.username or tr("new_account_label")

        reply = QMessageBox.question(
            self,
            tr("remove_account_title"),
            tr("remove_account_confirm", account=acc_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if draft.original_name:
            self.deleted_account_names.append(draft.original_name)
        elif draft.name and draft.has_stored_password:
            self.deleted_account_names.append(draft.name)

        self.account_drafts.pop(row)
        self.list_accounts.takeItem(row)

        new_count = len(self.account_drafts)
        if new_count == 0:
            self._current_account_index = -1
            self._clear_form()
            self.account_details_widget.setEnabled(False)
            self.btn_remove_account.setEnabled(False)
        else:
            new_row = min(row, new_count - 1)
            self.list_accounts.setCurrentRow(new_row)

    def _on_provider_changed(self, index: int) -> None:
        p_id = self.cb_provider.currentData()
        if not p_id:
            return
        provider = get_provider_by_id(p_id)
        lang = get_language()
        help_text = provider.help_text_pl if lang == "pl" else provider.help_text_en
        self.lbl_help.setText(help_text)

        if not self._is_updating_form and 0 <= self._current_account_index < len(
            self.account_drafts
        ):
            draft = self.account_drafts[self._current_account_index]
            draft.provider_id = p_id
            if provider.host:
                self.txt_host.setText(provider.host)
                draft.host = provider.host
                self.txt_port.setText(str(provider.port))
                draft.port = provider.port
                self.chk_ssl.setChecked(provider.use_ssl)
                draft.use_ssl = provider.use_ssl
            if provider.sent_folder:
                self.txt_sent_folder.setText(provider.sent_folder)
                draft.sent_folder = provider.sent_folder
            self._update_list_item(self._current_account_index)

    def _toggle_details(self) -> None:
        visible = not self.txt_details.isVisible()
        self.txt_details.setVisible(visible)
        self.btn_details.setText(tr("btn_hide_details") if visible else tr("btn_details"))

    def _on_account_input_changed(self) -> None:
        self.lbl_test_result.setText("")
        self.btn_details.setVisible(False)
        self.txt_details.setVisible(False)

        if self._is_updating_form:
            return

        if 0 <= self._current_account_index < len(self.account_drafts):
            draft = self.account_drafts[self._current_account_index]
            email = self.txt_email.text().strip()
            draft.name = email
            draft.username = email
            draft.host = self.txt_host.text().strip()
            try:
                draft.port = int(self.txt_port.text().strip())
            except ValueError:
                draft.port = 993
            draft.use_ssl = self.chk_ssl.isChecked()
            draft.sent_folder = self.txt_sent_folder.text().strip()
            pwd = self.txt_password.text()
            if pwd:
                draft.new_password = pwd
            else:
                draft.new_password = None
            self._update_list_item(self._current_account_index)
            self._update_password_status_label(draft)

    def _on_test_connection(self) -> None:
        email = self.txt_email.text().strip()
        pwd = self.txt_password.text()
        if not pwd and 0 <= self._current_account_index < len(self.account_drafts):
            draft = self.account_drafts[self._current_account_index]
            if draft.new_password:
                pwd = draft.new_password
            elif draft.original_name:
                pwd = self.secret_store.get(draft.original_name) or ""
            elif email:
                pwd = self.secret_store.get(email) or ""
        elif not pwd and email:
            pwd = self.secret_store.get(email) or ""

        host = self.txt_host.text().strip()
        try:
            port = int(self.txt_port.text().strip())
        except ValueError:
            port = 993

        self.btn_test.setEnabled(False)
        self.btn_details.setVisible(False)
        self.txt_details.setVisible(False)
        self.lbl_test_result.setStyleSheet(f"color: {theme.c('accent')};")
        self.lbl_test_result.setText(tr("step2_test_testing"))

        self.worker = ImapTestWorker(
            host=host,
            port=port,
            username=email,
            password=pwd,
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

    def _on_detect_models(self) -> None:
        if self.ollama_detect_worker and self.ollama_detect_worker.isRunning():
            return

        self.btn_detect_models.setEnabled(False)
        self.lbl_detect_status.setStyleSheet(f"color: {theme.c('muted')};")
        self.lbl_detect_status.setText(tr("ollama_detecting"))
        self.lbl_ollama_guide.setVisible(False)

        local_url = self.txt_local_url.text().strip() or self.config.ollama.local_url
        lan_url = self.txt_lan_url.text().strip() or self.config.ollama.lan_url

        self.ollama_detect_worker = OllamaDetectWorker(
            local_url=local_url,
            lan_url=lan_url,
            fetch_fn=self._ollama_fetch_fn,
        )
        self.ollama_detect_worker.finished_detection.connect(self._on_detection_finished)
        self.ollama_detect_worker.start()

    def _on_detection_finished(self, detection: Detection) -> None:
        self._ollama_detected_once = True
        self.ollama_detection = detection
        self.btn_detect_models.setEnabled(True)

        if detection.models:
            source_name = (
                tr("ollama_source_local")
                if detection.source == "local"
                else tr("ollama_source_lan")
            )
            self.lbl_detect_status.setStyleSheet(f"color: {theme.c('ok')};")
            self.lbl_detect_status.setText(
                tr("ollama_detected_server", source=source_name, count=len(detection.models))
            )
            self.lbl_ollama_guide.setVisible(False)
        else:
            self.lbl_detect_status.setStyleSheet(f"color: {theme.c('warn')};")
            self.lbl_detect_status.setText(tr("ollama_not_detected"))
            self.lbl_ollama_guide.setVisible(True)
            self.adv_ollama.setChecked(True)

        self._repopulate_model_combos()

    def _repopulate_model_combos(self) -> None:
        current_general = (
            self.cb_model.currentData() or self.cb_model.currentText() or self.config.ollama.model
        )
        current_polish = self.cb_polish_model.currentData()
        if current_polish is None and self.cb_polish_model.currentIndex() > 0:
            current_polish = self.cb_polish_model.currentText()
        if current_polish is None:
            current_polish = self.config.ollama.polish_model or ""

        installed = self.ollama_detection.models if self.ollama_detection else []
        show_all = self.chk_all_models.isChecked()
        available = get_available_models(installed, show_all=show_all)
        suggest = suggest_models(installed)

        self.cb_model.blockSignals(True)
        self.cb_polish_model.blockSignals(True)
        try:
            self.cb_model.clear()
            self.cb_polish_model.clear()

            # 1. Model ogólny
            for m in available:
                if suggest.general and m == suggest.general:
                    label = f"{m} {tr('ollama_recommended_tag')}"
                else:
                    label = m
                self.cb_model.addItem(label, userData=m)

            if current_general:
                status = (
                    describe_selection(current_general, installed)
                    if self.ollama_detection
                    else "ok"
                )
                has_item = any(
                    self.cb_model.itemData(i) == current_general
                    for i in range(self.cb_model.count())
                )
                if not has_item:
                    if status == "missing":
                        label = f"{current_general} {tr('ollama_model_missing_tag')}"
                    else:
                        label = current_general
                    self.cb_model.addItem(label, userData=current_general)

            target_idx = -1
            for i in range(self.cb_model.count()):
                if self.cb_model.itemData(i) == current_general:
                    target_idx = i
                    break
            if target_idx >= 0:
                self.cb_model.setCurrentIndex(target_idx)
            elif self.cb_model.count() > 0:
                self.cb_model.setCurrentIndex(0)

            # 2. Model do języka polskiego
            self.cb_polish_model.addItem(tr("ollama_same_as_general"), userData="")

            for m in available:
                if suggest.polish and m == suggest.polish:
                    label = f"{m} {tr('ollama_recommended_pl_tag')}"
                else:
                    label = m
                self.cb_polish_model.addItem(label, userData=m)

            if current_polish and current_polish != current_general:
                status_pl = (
                    describe_selection(current_polish, installed) if self.ollama_detection else "ok"
                )
                has_item_pl = any(
                    self.cb_polish_model.itemData(i) == current_polish
                    for i in range(self.cb_polish_model.count())
                )
                if not has_item_pl:
                    if status_pl == "missing":
                        label = f"{current_polish} {tr('ollama_model_missing_tag')}"
                    else:
                        label = current_polish
                    self.cb_polish_model.addItem(label, userData=current_polish)

            target_pl_idx = 0
            if current_polish and current_polish != current_general:
                for i in range(self.cb_polish_model.count()):
                    if self.cb_polish_model.itemData(i) == current_polish:
                        target_pl_idx = i
                        break
            self.cb_polish_model.setCurrentIndex(target_pl_idx)
        finally:
            self.cb_model.blockSignals(False)
            self.cb_polish_model.blockSignals(False)

        self._on_model_selection_changed()

    def _on_model_selection_changed(self) -> None:
        selected = self.cb_model.currentData() or self.cb_model.currentText()
        if not selected or not self.ollama_detection or not self.ollama_detection.models:
            self.lbl_model_warning.setVisible(False)
            return

        status = describe_selection(selected, self.ollama_detection.models)
        if status == "missing":
            self.lbl_model_warning.setText(tr("ollama_model_missing_warn", model=selected))
            self.lbl_model_warning.setVisible(True)
        else:
            self.lbl_model_warning.setVisible(False)

    def _on_check_model(self) -> None:
        if self.ollama_check_worker and self.ollama_check_worker.isRunning():
            return

        selected_model = self.cb_model.currentData() or self.cb_model.currentText()
        if not selected_model:
            return

        self.btn_check_model.setEnabled(False)
        self.lbl_check_result.setStyleSheet(f"color: {theme.c('muted')};")
        self.lbl_check_result.setText(tr("ollama_checking"))

        prefer = (
            "local"
            if (self.ollama_detection and self.ollama_detection.local_ok)
            else (
                "lan"
                if (self.ollama_detection and self.ollama_detection.lan_ok)
                else self.config.ollama.prefer
            )
        )
        cfg = OllamaConfig(
            lan_url=self.txt_lan_url.text().strip() or self.config.ollama.lan_url,
            local_url=self.txt_local_url.text().strip() or self.config.ollama.local_url,
            model=selected_model,
            polish_model=selected_model,
            prefer=prefer,
            timeout_s=15.0,
        )

        lang = get_language()
        self.ollama_check_worker = OllamaCheckWorker(
            cfg=cfg,
            model=selected_model,
            client_factory=self._ollama_client_factory,
            lang=lang,
        )
        self.ollama_check_worker.finished_check.connect(self._on_check_model_finished)
        self.ollama_check_worker.start()

    def _on_check_model_finished(self, result: CheckResult) -> None:
        self.btn_check_model.setEnabled(True)
        if result.ok:
            self.lbl_check_result.setStyleSheet(f"color: {theme.c('ok')};")
        else:
            self.lbl_check_result.setStyleSheet(f"color: {theme.c('error')};")
        self.lbl_check_result.setText(result.message)

    def closeEvent(self, event) -> None:
        if self.ollama_detect_worker and self.ollama_detect_worker.isRunning():
            self.ollama_detect_worker.wait(1000)
        if self.ollama_check_worker and self.ollama_check_worker.isRunning():
            self.ollama_check_worker.wait(1000)
        super().closeEvent(event)

    def _on_save(self) -> None:
        if 0 <= self._current_account_index < len(self.account_drafts):
            self._save_form_to_draft(self._current_account_index)

        # Walidacja kont
        seen_names: set[str] = set()
        for idx, draft in enumerate(self.account_drafts):
            email = draft.username.strip()
            if not email:
                QMessageBox.warning(self, "MailVoice", tr("account_empty_email_error"))
                self.list_accounts.setCurrentRow(idx)
                self.txt_email.setFocus()
                return

            email_lower = email.lower()
            if email_lower in seen_names:
                QMessageBox.warning(self, "MailVoice", tr("account_duplicate_error", account=email))
                self.list_accounts.setCurrentRow(idx)
                return
            seen_names.add(email_lower)

            if draft.port < 1 or draft.port > 65535:
                QMessageBox.warning(
                    self, "MailVoice", tr("account_invalid_port_error", account=email)
                )
                self.list_accounts.setCurrentRow(idx)
                self.txt_port.setFocus()
                return

            if not draft.use_ssl:
                QMessageBox.warning(
                    self, "MailVoice", tr("account_ssl_required_error", account=email)
                )
                self.list_accounts.setCurrentRow(idx)
                return

        # Migracja i aktualizacja sekretów w SecretStore
        active_names = {draft.name for draft in self.account_drafts}
        for name in self.deleted_account_names:
            if name not in active_names:
                try:
                    self.secret_store.delete(name)
                except Exception:
                    pass

        for draft in self.account_drafts:
            old_name = draft.original_name
            new_name = draft.name

            if old_name and old_name != new_name:
                old_secret = self.secret_store.get(old_name)
                pwd_to_save = draft.new_password if draft.new_password is not None else old_secret
                if pwd_to_save:
                    self.secret_store.set(new_name, pwd_to_save)
                self.secret_store.delete(old_name)
                draft.original_name = new_name
            else:
                if draft.new_password is not None:
                    self.secret_store.set(new_name, draft.new_password)

        new_accounts: list[AccountConfig] = []
        for draft in self.account_drafts:
            provider = get_provider_by_id(draft.provider_id)
            sent_f = draft.sent_folder.strip() or provider.sent_folder
            new_accounts.append(
                AccountConfig(
                    name=draft.name,
                    host=draft.host or provider.host,
                    port=draft.port,
                    username=draft.username,
                    use_ssl=draft.use_ssl,
                    folders=draft.folders or ["INBOX"],
                    sent_folder=sent_f,
                )
            )

        vip_senders = [self.list_vip.item(i).text() for i in range(self.list_vip.count())]
        keywords = [self.list_kw.item(i).text() for i in range(self.list_kw.count())]

        # Walidacja i konfiguracja Ollama
        selected_model = (
            self.cb_model.currentData() or self.cb_model.currentText() or self.config.ollama.model
        )
        selected_polish_data = self.cb_polish_model.currentData()
        if not selected_polish_data:
            selected_polish = selected_model
        else:
            selected_polish = selected_polish_data

        if self.ollama_detection is not None and (
            self.ollama_detection.local_ok or self.ollama_detection.lan_ok
        ):
            status = describe_selection(selected_model, self.ollama_detection.models)
            if status == "missing":
                ans = QMessageBox.question(
                    self,
                    "MailVoice",
                    tr("ollama_model_missing_confirm", model=selected_model),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    self.tabs.setCurrentWidget(self._ollama_page)
                    return

        prefer = (
            ("local" if self.ollama_detection.local_ok else "lan")
            if self.ollama_detection is not None
            else self.config.ollama.prefer
        )

        ollama_cfg = OllamaConfig(
            lan_url=self.txt_lan_url.text().strip() or self.config.ollama.lan_url,
            local_url=self.txt_local_url.text().strip() or self.config.ollama.local_url,
            model=selected_model,
            polish_model=selected_polish,
            prefer=prefer,
            timeout_s=self.config.ollama.timeout_s,
        )

        server_cfg = ServerConfig(
            enabled=self.cb_server_enabled.isChecked(),
            port=self.config.server.port,
            bind=self.config.server.bind,
            max_devices=self.config.server.max_devices,
        )

        new_config = AppConfig(
            accounts=new_accounts,
            analysis_prompt=self.txt_desc.toPlainText().strip(),
            vip_senders=vip_senders,
            keywords=keywords,
            blocked_senders=[],  # przeniesione do ignore_rules (to samo działanie)
            ignore_rules=self._collect_ignore_rules(),
            interval_minutes=self.cb_interval.currentData() or 10,
            notify_mode="ask" if self.rb_ask.isChecked() else "beep",
            voice_output=self.cb_voice_output.currentData() or "auto",
            auto_vip=self.cb_auto_vip.currentData() or "bonus",
            beep_repeat_minutes=self.config.beep_repeat_minutes,
            ask_retry_minutes=self.config.ask_retry_minutes,
            importance_threshold=self.slider.value(),
            backlog_days=self.config.backlog_days,
            language=self.config.language,
            index_retention_days=self.config.index_retention_days,
            digest_days=self.spin_digest_days.value(),
            my_addresses=self.config.my_addresses,
            ollama=ollama_cfg,
            server=server_cfg,
        )

        try:
            save_config(new_config, self.config_path)
            if self.on_config_saved:
                self.on_config_saved(new_config)
            QMessageBox.information(self, "MailVoice", tr("save_success"))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "MailVoice", f"Błąd zapisu: {exc}")
