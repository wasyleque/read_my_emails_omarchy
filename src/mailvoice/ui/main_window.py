"""Główne okno aplikacji MailVoice z listą ważnych maili i obsługą zasobnika."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import platformdirs
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.config import AppConfig, save_config
from mailvoice.core.contacts import ContactCard
from mailvoice.core.digest import Digest, Topic
from mailvoice.core.friendly_errors import format_friendly_error
from mailvoice.core.phishing import defang_url
from mailvoice.core.pipeline import CycleResult, PendingBacklog, ProcessedMail
from mailvoice.core.service import (
    AskReminder,
    BacklogQuestion,
    BeepReminder,
    ContactCardReady,
    DigestReady,
    Event,
    MailService,
    NewImportant,
    SearchResults,
    ServiceError,
    SuspiciousMail,
)
from mailvoice.core.summarizer import summarize
from mailvoice.ui import theme
from mailvoice.ui.i18n import get_language, tr
from mailvoice.ui.search_dialog import SearchDialog
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.beeper import Beeper
from mailvoice.voice.dialog import VoiceDialog
from mailvoice.voice.tts import Speaker, VoiceUnavailable


class CycleWorker(QThread):
    """Wątek roboczy wykonujący pobieranie i analizę poczty w tle."""

    cycle_finished = Signal(object)
    cycle_error = Signal(str)

    def __init__(self, service: MailService, check_backlog: bool = False) -> None:
        super().__init__()
        self.service = service
        self.check_backlog = check_backlog

    def run(self) -> None:
        try:
            result = self.service.trigger_cycle(check_backlog=self.check_backlog)
            self.cycle_finished.emit(result)
        except Exception as exc:
            self.cycle_error.emit(str(exc))


class DigestWorker(QThread):
    """Wątek roboczy generujący podsumowanie tematów w tle."""

    digest_ready = Signal(object)
    digest_error = Signal(str)

    def __init__(self, service: MailService, days: int | None = None) -> None:
        super().__init__()
        self.service = service
        self.days = days

    def run(self) -> None:
        try:
            digest = self.service.request_digest(self.days)
            self.digest_ready.emit(digest)
        except Exception as exc:
            self.digest_error.emit(str(exc))


class ContactWorker(QThread):
    """Wątek roboczy pobierający kontekst kontaktu w tle."""

    card_ready = Signal(object, str)

    def __init__(self, service: MailService, sender: str) -> None:
        super().__init__()
        self.service = service
        self.sender = sender

    def run(self) -> None:
        try:
            card = self.service.contact_context(self.sender)
            self.card_ready.emit(card, self.sender)
        except Exception:
            self.card_ready.emit(None, self.sender)


class ServiceEventBridge(QObject):
    """Mostek przekazujący zdarzenia z serwisu do głównego wątku Qt za pomocą sygnałów."""

    new_event = Signal(object)


class MainWindow(QMainWindow):
    """Główne okno interfejsu użytkownika MailVoice."""

    def __init__(
        self,
        service: MailService | None = None,
        config_path: Path | None = None,
        speaker: Speaker | None = None,
        beeper: Beeper | None = None,
        voice_dialog: VoiceDialog | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.config_path = config_path or (
            Path(platformdirs.user_config_dir("mailvoice")) / "config.json"
        )
        self.speaker = speaker
        self.beeper = beeper
        self.voice_dialog = voice_dialog

        self.bridge = ServiceEventBridge()
        self.bridge.new_event.connect(self._handle_service_event)

        if self.service:
            self.service.add_listener(self._on_service_event)

        self.worker: CycleWorker | None = None
        self.digest_worker: DigestWorker | None = None
        self.contact_worker: ContactWorker | None = None
        self.current_digest: Digest | None = None
        self.current_context_card: ContactCard | None = None
        self.current_context_sender: str = ""
        self.important_items: list[ProcessedMail] = []
        self._is_muted = False

        self.setWindowTitle(tr("app_title"))
        self.resize(840, 600)
        self._init_ui()
        self._init_tray()
        self._init_timer()
        if self.service and not self.service.config.accounts:
            self.lbl_status.setText(tr("status_no_accounts"))

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        # Pasek statusu u góry
        status_bar_layout = QHBoxLayout()
        self.lbl_status = QLabel(tr("status_ready"))
        self.lbl_status.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {theme.c('accent')};"
        )
        status_bar_layout.addWidget(self.lbl_status)
        self._last_error_details = ""
        self.btn_error_details = QPushButton(tr("btn_details"))
        self.btn_error_details.setVisible(False)
        self.btn_error_details.clicked.connect(self._show_error_details)
        status_bar_layout.addWidget(self.btn_error_details)
        status_bar_layout.addStretch()

        self.lbl_last_check = QLabel(f"{tr('status_last_check')} {tr('status_never')}")
        self.lbl_last_check.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        status_bar_layout.addWidget(self.lbl_last_check)
        layout.addLayout(status_bar_layout)

        # Zakładki: Wiadomości i Podsumowanie
        self.tabs = QTabWidget(self)

        # Zakładka 1: Wiadomości
        self.tab_messages = QWidget()
        msg_layout = QVBoxLayout(self.tab_messages)

        lbl_section = QLabel(tr("section_important"))
        lbl_section.setStyleSheet("font-weight: bold; margin-top: 4px; margin-bottom: 4px;")
        msg_layout.addWidget(lbl_section)

        self.tbl_mails = QTableWidget(0, 5)
        self.tbl_mails.setHorizontalHeaderLabels(
            [
                tr("col_sender"),
                tr("col_subject"),
                tr("col_reason"),
                tr("col_account"),
                tr("col_actions"),
            ]
        )
        header = self.tbl_mails.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        if not self.service or len(self.service.config.accounts) <= 1:
            self.tbl_mails.setColumnHidden(3, True)
        self.tbl_mails.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_mails.itemSelectionChanged.connect(self._on_mail_selection_changed)
        msg_layout.addWidget(self.tbl_mails)

        # Panel kontekstu nadawcy
        self.group_context = QGroupBox(tr("context_panel_title"))
        self.group_context.setStyleSheet(
            f"QGroupBox {{ font-weight: bold; margin-top: 4px; "
            f"border: 1px solid {theme.c('card_border')}; "
            "border-radius: 6px; padding-top: 14px; }"
        )
        self.group_context.setMinimumHeight(190)  # cały kontekst ma być widoczny, nie ucięty
        ctx_layout = QVBoxLayout(self.group_context)

        self.lbl_context_details = QLabel(tr("context_select_mail"))
        self.lbl_context_details.setWordWrap(True)
        self.lbl_context_details.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.lbl_context_details.setStyleSheet(
            f"font-size: 12px; color: {theme.c('text')}; margin: 4px;"
        )
        ctx_layout.addWidget(self.lbl_context_details)

        ctx_btn_row = QHBoxLayout()
        ctx_btn_row.addStretch()
        self.btn_context_search = QPushButton(tr("btn_search_ai"))
        self.btn_context_search.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.btn_context_search.clicked.connect(self._on_context_search_clicked)
        self.btn_context_search.setEnabled(False)
        ctx_btn_row.addWidget(self.btn_context_search)
        ctx_layout.addLayout(ctx_btn_row)

        msg_layout.addWidget(self.group_context)

        self.tabs.addTab(self.tab_messages, tr("tab_messages"))

        # Zakładka 2: Podsumowanie tematów
        self.tab_digest = QWidget()
        self._init_digest_tab()
        self.tabs.addTab(self.tab_digest, tr("tab_digest"))

        layout.addWidget(self.tabs)

        # Dolny pasek przycisków
        btn_layout = QHBoxLayout()

        self.btn_check_now = QPushButton(tr("btn_check_now"))
        self.btn_check_now.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.btn_check_now.clicked.connect(self._on_check_now)
        btn_layout.addWidget(self.btn_check_now)

        self.btn_mute = QPushButton(tr("btn_mute"))
        self.btn_mute.clicked.connect(self._toggle_mute)
        btn_layout.addWidget(self.btn_mute)

        self.btn_ai_search = QPushButton(tr("btn_search_ai"))
        self.btn_ai_search.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.btn_ai_search.clicked.connect(lambda: self._open_ai_search())
        btn_layout.addWidget(self.btn_ai_search)

        btn_layout.addStretch()

        self.btn_settings = QPushButton(tr("btn_settings"))
        self.btn_settings.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.btn_settings.clicked.connect(self._open_settings)
        btn_layout.addWidget(self.btn_settings)

        layout.addLayout(btn_layout)
        self.setCentralWidget(central_widget)

    def _init_digest_tab(self) -> None:
        """Inicjalizacja zakładki podsumowania tematów (Digest)."""
        layout = QVBoxLayout(self.tab_digest)

        # Pasek wyboru zakresu i odświeżania
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel(tr("digest_timeframe_label")))

        self.cb_digest_period = QComboBox()
        self.cb_digest_period.addItem(tr("digest_period_week"), 7)
        self.cb_digest_period.addItem(tr("digest_period_month"), 30)
        self.cb_digest_period.addItem(tr("digest_period_quarter"), 90)
        self.cb_digest_period.setCurrentIndex(1)  # Domyślnie 30 dni
        ctrl_layout.addWidget(self.cb_digest_period)

        self.btn_refresh_digest = QPushButton(tr("btn_refresh_digest"))
        self.btn_refresh_digest.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.btn_refresh_digest.clicked.connect(self._on_refresh_digest)
        ctrl_layout.addWidget(self.btn_refresh_digest)

        self.lbl_digest_status = QLabel("")
        self.lbl_digest_status.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        ctrl_layout.addWidget(self.lbl_digest_status)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Obszar przewijania dla kart tematów
        self.scroll_digest = QScrollArea()
        self.scroll_digest.setWidgetResizable(True)
        self.digest_container = QWidget()
        self.digest_layout = QVBoxLayout(self.digest_container)
        self.digest_layout.setContentsMargins(4, 4, 4, 4)

        lbl_init = QLabel(tr("digest_empty"))
        lbl_init.setStyleSheet(f"color: {theme.c('muted')}; font-size: 13px; margin: 20px;")
        self.digest_layout.addWidget(lbl_init)
        self.digest_layout.addStretch()

        self.scroll_digest.setWidget(self.digest_container)
        layout.addWidget(self.scroll_digest)

    def _init_tray(self) -> None:
        """Inicjalizacja ikony w zasobniku systemowym."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip(tr("tray_tooltip"))

        menu = QMenu(self)
        act_show = QAction(tr("tray_show"), self)
        act_show.triggered.connect(self._show_from_tray)
        menu.addAction(act_show)

        act_check = QAction(tr("btn_check_now"), self)
        act_check.triggered.connect(self._on_check_now)
        menu.addAction(act_check)

        menu.addSeparator()
        act_quit = QAction(tr("tray_exit"), self)
        act_quit.triggered.connect(self._quit_application)
        menu.addAction(act_quit)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _init_timer(self) -> None:
        """Okresowy timer Qt wołający tick w MailService."""
        self.timer = QTimer(self)
        self.timer.setInterval(30 * 1000)  # Sprawdzanie co 30 sekund
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start()

    def _on_timer_tick(self) -> None:
        if self.service:
            # Sprawdzamy czy nadszedł czas na pobranie
            now = datetime.now(timezone.utc)
            if self.worker is None or not self.worker.isRunning():
                # Uruchamiamy sprawdzanie w tle, jeśli tick tego wymaga
                last = self.service.last_cycle_time
                interval = self.service.config.interval_minutes
                if last is None or (now.timestamp() - last.timestamp()) >= interval * 60:
                    self._start_cycle_worker(check_backlog=False)
                else:
                    self.service.tick(now)

    def _on_check_now(self) -> None:
        """Ręczne wymuszenie sprawdzenia poczty."""
        if self.worker is not None and self.worker.isRunning():
            return
        self._start_cycle_worker(check_backlog=False)

    def _start_cycle_worker(self, check_backlog: bool = False) -> None:
        if not self.service:
            return
        if not self.service.config.accounts:
            self.lbl_status.setText(tr("status_no_accounts"))
            self.btn_check_now.setEnabled(True)
            return
        self.lbl_status.setText(tr("status_checking"))
        self.btn_error_details.setVisible(False)
        self.btn_check_now.setEnabled(False)

        self.worker = CycleWorker(self.service, check_backlog=check_backlog)
        self.worker.cycle_finished.connect(self._on_cycle_finished)
        self.worker.cycle_error.connect(self._on_cycle_error)
        self.worker.start()

    def _on_cycle_finished(self, result: CycleResult) -> None:
        self.btn_check_now.setEnabled(True)
        now_str = datetime.now().strftime("%H:%M")
        self.lbl_status.setText(tr("status_ready"))
        self.lbl_last_check.setText(f"{tr('status_last_check')} {now_str}")

        if result.important:
            for item in result.important:
                self._add_important_mail(item)

        if result.suspicious:
            for item in result.suspicious:
                self._add_important_mail(item)

    def _show_problem(self, raw_message: str) -> None:
        """Pokazuje prosty komunikat w pasku statusu i przycisk ze szczegółami technicznymi."""
        friendly = format_friendly_error(raw_message, lang=get_language())
        self.lbl_status.setText(f"Problem: {friendly}")
        self._last_error_details = str(raw_message)
        self.btn_error_details.setVisible(True)

    def _show_error_details(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("MailVoice")
        box.setText(tr("btn_details"))
        box.setDetailedText(self._last_error_details)
        box.exec()

    def _on_cycle_error(self, err_msg: str) -> None:
        self.btn_check_now.setEnabled(True)
        self._show_problem(err_msg)

    def _add_important_mail(self, item: ProcessedMail) -> None:
        if any(
            x.account == item.account and x.folder == item.folder and x.uid == item.uid
            for x in self.important_items
        ):
            return
        self.important_items.append(item)
        row = self.tbl_mails.rowCount()
        self.tbl_mails.insertRow(row)

        sender_text = item.mail.sender
        subject_text = item.mail.subject
        if item.suspicious:
            sender_text = f"⚠ {sender_text}"
            subject_text = f"[{tr('badge_suspicious')}] {subject_text}"
            reasons_str = (
                "; ".join(item.risk_reasons) if item.risk_reasons else item.analysis_reason
            )
            reason = f"{tr('badge_suspicious')}: {reasons_str}"
        else:
            reason = item.analysis_reason or "; ".join(item.rule_reasons)

        self.tbl_mails.setItem(row, 0, QTableWidgetItem(sender_text))
        self.tbl_mails.setItem(row, 1, QTableWidgetItem(subject_text))
        self.tbl_mails.setItem(row, 2, QTableWidgetItem(reason))
        self.tbl_mails.setItem(row, 3, QTableWidgetItem(item.account))

        btn_listen = QPushButton(tr("btn_listen_summary"))
        btn_listen.clicked.connect(lambda _, m=item: self._listen_to_mail(m))
        self.tbl_mails.setCellWidget(row, 4, btn_listen)

    def _listen_to_mail(self, item: ProcessedMail) -> None:
        """Odtwarza streszczenie wybranego maila."""
        if not self.speaker:
            return
        lang = item.language if item.language in ("pl", "en") else get_language()

        if item.suspicious:
            if lang == "pl":
                msg = "Uwaga, ta wiadomość wygląda na podejrzaną, nie czytam jej treści."
            else:
                msg = "Warning: this message looks suspicious, not reading its content."
            try:
                self.speaker.speak(msg, lang=lang)
            except VoiceUnavailable:
                pass
            reasons_list = [defang_url(r) for r in item.risk_reasons]
            reasons_formatted = "\n• " + "\n• ".join(reasons_list) if reasons_list else ""
            info = (
                f"{tr('suspicious_warning_dialog')}\n\n"
                f"{tr('suspicious_reasons_title')}{reasons_formatted}"
            )
            QMessageBox.warning(self, tr("badge_suspicious"), info)
            return

        if self.service:
            try:
                summary = summarize(
                    self.service.ollama_client, self.service.config, item.mail, language=lang
                )
            except Exception:
                summary = item.analysis_reason or item.mail.body_text[:200]
        else:
            summary = item.analysis_reason or item.mail.body_text[:200]

        if lang == "pl":
            header = f"Od {item.mail.sender}. Temat: {item.mail.subject}. "
        else:
            header = f"From {item.mail.sender}. Subject: {item.mail.subject}. "
        try:
            self.speaker.speak(header + summary, lang=lang)
        except VoiceUnavailable as exc:
            QMessageBox.warning(self, "MailVoice", str(exc))

    def _toggle_mute(self) -> None:
        self._is_muted = not self._is_muted
        if self._is_muted:
            if self.service:
                self.service.user_dismiss()
            self.btn_mute.setText(tr("btn_unmute"))
            self.btn_mute.setStyleSheet(f"background-color: {theme.c('mute_bg')};")
        else:
            self.btn_mute.setText(tr("btn_mute"))
            self.btn_mute.setStyleSheet("")

    def _open_settings(self) -> None:
        if not self.service:
            return
        dlg = SettingsDialog(
            config=self.service.config,
            config_path=self.config_path,
            secret_store=self.service.secret_store,
            speaker=self.speaker,
            on_config_saved=self._on_config_updated,
            parent=self,
        )
        dlg.exec()

    def _on_config_updated(self, new_config: AppConfig) -> None:
        if self.service:
            self.service.update_config(new_config)
            save_config(new_config, self.config_path)
            self.tbl_mails.setColumnHidden(3, len(new_config.accounts) <= 1)
            if not new_config.accounts:
                self.lbl_status.setText(tr("status_no_accounts"))
            elif self.lbl_status.text() == tr("status_no_accounts"):
                self.lbl_status.setText(tr("status_ready"))

    def _on_service_event(self, event: Event) -> None:
        """Odbiera zdarzenie z wątku serwisu i emituje sygnał do GUI."""
        self.bridge.new_event.emit(event)

    def _handle_service_event(self, event: Event) -> None:
        """Obsługa zdarzeń serwisu w głównym wątku Qt."""
        if isinstance(event, NewImportant):
            for item in event.items:
                self._add_important_mail(item)
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)

        elif isinstance(event, SuspiciousMail):
            self._add_important_mail(event.mail)
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)

        elif isinstance(event, BacklogQuestion):
            if not self._is_muted:
                self._ask_backlog(event.items, event.count)

        elif isinstance(event, (BeepReminder, AskReminder)):
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)
            elif isinstance(event, BeepReminder) and self.beeper and not self._is_muted:
                self.beeper.beep()

        elif isinstance(event, ServiceError):
            self._show_problem(event.message)

        elif isinstance(event, DigestReady):
            self._display_digest(event.digest)
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)

        elif isinstance(event, ContactCardReady):
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)

        elif isinstance(event, SearchResults):
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)

    def _on_mail_selection_changed(self) -> None:
        """Obsługuje zaznaczenie wiersza w tabeli wiadomości."""
        selected_indexes = self.tbl_mails.selectedIndexes()
        if not selected_indexes:
            self.current_context_card = None
            self.current_context_sender = ""
            self.lbl_context_details.setText(tr("context_select_mail"))
            self.btn_context_search.setEnabled(False)
            return

        row = selected_indexes[0].row()
        if 0 <= row < len(self.important_items):
            item = self.important_items[row]
            self._load_contact_context(item.mail.sender)

    def _load_contact_context(self, sender: str) -> None:
        """Pobiera i wyświetla kartę kontaktu dla wskazanego nadawcy."""
        self.current_context_sender = sender
        self.lbl_context_details.setText(tr("context_loading"))
        self.btn_context_search.setEnabled(False)

        if not self.service:
            self._display_contact_card(None, sender)
            return

        if self.contact_worker is not None and self.contact_worker.isRunning():
            self.contact_worker.wait()

        self.contact_worker = ContactWorker(self.service, sender)
        self.contact_worker.card_ready.connect(self._on_contact_card_ready)
        self.contact_worker.start()

    def _on_contact_card_ready(self, card: ContactCard | None, sender: str) -> None:
        if sender == self.current_context_sender:
            self._display_contact_card(card, sender)

    def _display_contact_card(self, card: ContactCard | None, sender: str) -> None:
        """Wyświetla podsumowanie karty kontaktu w panelu kontekstu."""
        import html

        self.current_context_card = card
        safe_sender = html.escape(defang_url(sender))
        if card is None:
            muted = theme.c("muted")
            self.lbl_context_details.setText(
                f"<span style='color: {muted};'>{tr('context_unknown_sender')}</span><br>"
                f"<span style='font-size: 11px; color: {muted};'>Adres: {safe_sender}</span>"
            )
            self.btn_context_search.setText(tr("btn_search_ai"))
            self.btn_context_search.setEnabled(True)
            return

        safe_name = html.escape(card.name)
        safe_addrs = html.escape(", ".join(defang_url(a) for a in card.addresses))
        lines = [
            f"<b>{safe_name}</b> <span style='color: {theme.c('muted')};'>({safe_addrs})</span>",
        ]
        if card.relationship_hint:
            safe_hint = html.escape(defang_url(card.relationship_hint))
            lines.append(f"<b>{tr('context_relationship')}</b> {safe_hint}")
        if card.why_it_matters:
            safe_why = html.escape(defang_url(card.why_it_matters))
            lines.append(f"<b>{tr('col_reason')}:</b> {safe_why}")
        if card.open_items:
            open_str = html.escape("; ".join(defang_url(item) for item in card.open_items))
            lines.append(f"<b>{tr('context_open_items')}</b> {open_str}")
        if card.last_exchange:
            _, dir_text, s_text = card.last_exchange[0]
            safe_dt = html.escape(dir_text)
            safe_st = html.escape(defang_url(s_text))
            lines.append(f"<b>{tr('context_last_exchange')}</b> {safe_dt}: {safe_st}")

        self.lbl_context_details.setText("<br>".join(lines))
        self.btn_context_search.setText(tr("btn_search_ai"))
        self.btn_context_search.setToolTip(card.name)
        self.btn_context_search.setEnabled(True)

    def _on_context_search_clicked(self) -> None:
        """Otwiera dialog wyszukiwania AI z kontekstem bieżącego kontaktu."""
        query = ""
        if self.current_context_card:
            query = f"maile od {self.current_context_card.name}"
        elif self.current_context_sender:
            query = f"mail od {self.current_context_sender}"
        self._open_ai_search(query)

    def _open_ai_search(self, initial_query: str = "") -> None:
        """Otwiera okno dialogowe inteligentnego wyszukiwania wiadomości."""
        dlg = SearchDialog(
            service=self.service,
            speaker=self.speaker,
            parent=self,
        )
        if initial_query:
            dlg.set_search_query(initial_query, auto_search=True)
        dlg.exec()

    def _on_refresh_digest(self) -> None:
        """Uruchamia odświeżenie podsumowania tematów w tle."""
        if not self.service:
            return
        if self.digest_worker is not None and self.digest_worker.isRunning():
            return
        days = self.cb_digest_period.currentData() or self.service.config.digest_days
        self.lbl_digest_status.setText(tr("digest_status_loading"))
        self.btn_refresh_digest.setEnabled(False)

        self.digest_worker = DigestWorker(self.service, days=days)
        self.digest_worker.digest_ready.connect(self._on_digest_ready)
        self.digest_worker.digest_error.connect(self._on_digest_error)
        self.digest_worker.start()

    def _on_digest_ready(self, digest: Digest) -> None:
        self.btn_refresh_digest.setEnabled(True)
        self._display_digest(digest)

    def _on_digest_error(self, err_msg: str) -> None:
        self.btn_refresh_digest.setEnabled(True)
        friendly = format_friendly_error(err_msg, lang=get_language())
        self.lbl_digest_status.setText(f"Problem: {friendly}")

    def _display_digest(self, digest: Digest) -> None:
        """Renderuje karty tematów w zakładce podsumowania."""
        self.current_digest = digest
        self.lbl_digest_status.setText(f"{tr('status_ready')} ({digest.period})")
        self.btn_refresh_digest.setEnabled(True)

        while self.digest_layout.count():
            item = self.digest_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not digest.topics:
            lbl_empty = QLabel(tr("digest_empty"))
            lbl_empty.setStyleSheet(f"color: {theme.c('muted')}; font-size: 13px; margin: 20px;")
            self.digest_layout.addWidget(lbl_empty)
            self.digest_layout.addStretch()
            return

        waiting_me = [t for t in digest.topics if t.status == "oczekuje_na_mnie"]
        waiting_others = [t for t in digest.topics if t.status == "oczekuje_na_innych"]
        info_topics = [t for t in digest.topics if t.status in ("informacyjne", "zamknięte")]

        self._add_digest_group(
            tr("digest_group_waiting_me"), waiting_me, border_color=theme.c("accent")
        )
        self._add_digest_group(
            tr("digest_group_waiting_others"), waiting_others, border_color=theme.c("warn")
        )
        self._add_digest_group(tr("digest_group_info"), info_topics, border_color=theme.c("muted"))
        self.digest_layout.addStretch()

    def _add_digest_group(self, title: str, topics: list[Topic], border_color: str = "") -> None:
        """Dodaje sekcję grupującą karty tematów."""
        group = QGroupBox(f"{title} ({len(topics)})")
        group.setStyleSheet(
            f"QGroupBox {{ font-weight: bold; margin-top: 8px; border: 1px solid {border_color}; "
            f"border-radius: 6px; padding-top: 14px; }}"
        )
        grp_layout = QVBoxLayout(group)

        if not topics:
            lbl_none = QLabel(tr("digest_no_topics_in_group"))
            lbl_none.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px; margin: 4px;")
            grp_layout.addWidget(lbl_none)
        else:
            for topic in topics:
                card = QFrame()
                card.setFrameShape(QFrame.Shape.StyledPanel)
                card.setObjectName("card")
                card.setStyleSheet(
                    f"QFrame#card {{ background-color: {theme.c('card_bg')}; "
                    f"border: 1px solid {theme.c('card_border')}; "
                    "border-radius: 6px; margin-bottom: 6px; padding: 6px; }"
                )
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(8, 6, 8, 6)

                header_layout = QHBoxLayout()
                lbl_title = QLabel(topic.title)
                lbl_title.setStyleSheet(
                    f"font-weight: bold; font-size: 13px; color: {theme.c('text')};"
                )
                header_layout.addWidget(lbl_title)
                header_layout.addStretch()

                btn_listen = QPushButton(tr("digest_btn_listen"))
                btn_listen.clicked.connect(lambda _, t=topic: self._listen_to_topic(t))
                header_layout.addWidget(btn_listen)
                card_layout.addLayout(header_layout)

                if topic.who_to_whom:
                    w2w_text = "; ".join(topic.who_to_whom)
                    lbl_w2w = QLabel(f"<b>{tr('digest_who_to_whom')}:</b> {w2w_text}")
                    lbl_w2w.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
                    card_layout.addWidget(lbl_w2w)

                if topic.why:
                    lbl_why = QLabel(f"<b>{tr('col_reason')}:</b> {topic.why}")
                    lbl_why.setStyleSheet(f"color: {theme.c('text')}; font-size: 12px;")
                    card_layout.addWidget(lbl_why)

                grp_layout.addWidget(card)

        self.digest_layout.addWidget(group)

    def _listen_to_topic(self, topic: Topic) -> None:
        """Odtwarza streszczenie wybranego tematu na głos."""
        if not self.speaker:
            return
        lang = get_language()
        w2w = f" {topic.who_to_whom[0]}." if topic.who_to_whom else ""
        why_text = f" {topic.why}" if topic.why else ""
        if lang == "pl":
            st_text = {
                "oczekuje_na_mnie": "Czeka na Twoją odpowiedź.",
                "oczekuje_na_innych": "Czeka na odpowiedź innych.",
                "zamknięte": "Sprawa zakończona.",
                "informacyjne": "Wiadomość informacyjna.",
            }.get(topic.status, "")
            text = f"Temat: {topic.title}.{w2w}{why_text} {st_text}"
        else:
            st_text = {
                "oczekuje_na_mnie": "Waiting for your response.",
                "oczekuje_na_innych": "Waiting for others to respond.",
                "zamknięte": "Topic closed.",
                "informacyjne": "Informational message.",
            }.get(topic.status, "")
            text = f"Topic: {topic.title}.{w2w}{why_text} {st_text}"
        try:
            self.speaker.speak(" ".join(text.split()), lang=lang)
        except VoiceUnavailable as exc:
            QMessageBox.warning(self, "MailVoice", str(exc))

    def _ask_backlog(self, items: Sequence[ProcessedMail | PendingBacklog], count: int) -> None:
        """Wyświetla okno dialogowe z pytaniem o zaległe nieprzeczytane wiadomości."""
        msg = tr("backlog_dialog_msg", count=count)
        reply = QMessageBox.question(
            self,
            tr("backlog_dialog_title"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        accepted = reply == QMessageBox.StandardButton.Yes
        if self.service:
            self.service.resolve_backlog(accepted, items)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_application(self) -> None:
        if self.tray_icon:
            self.tray_icon.hide()
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Minimalizuje do zasobnika systemowego, jeśli dostępny."""
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()
