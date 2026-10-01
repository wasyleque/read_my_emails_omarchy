"""Główne okno aplikacji MailVoice z listą ważnych maili i obsługą zasobnika."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.config import AppConfig, save_config
from mailvoice.core.friendly_errors import format_friendly_error
from mailvoice.core.pipeline import CycleResult, PendingBacklog, ProcessedMail
from mailvoice.core.service import (
    AskReminder,
    BacklogQuestion,
    BeepReminder,
    Event,
    MailService,
    NewImportant,
    ServiceError,
)
from mailvoice.core.summarizer import summarize
from mailvoice.ui.i18n import get_language, tr
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
        self.config_path = config_path or Path("config.json")
        self.speaker = speaker
        self.beeper = beeper
        self.voice_dialog = voice_dialog

        self.bridge = ServiceEventBridge()
        self.bridge.new_event.connect(self._handle_service_event)

        if self.service:
            self.service.add_listener(self._on_service_event)

        self.worker: CycleWorker | None = None
        self.important_items: list[ProcessedMail] = []
        self._is_muted = False

        self.setWindowTitle(tr("app_title"))
        self.resize(780, 520)
        self._init_ui()
        self._init_tray()
        self._init_timer()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        # Pasek statusu u góry
        status_bar_layout = QHBoxLayout()
        self.lbl_status = QLabel(tr("status_ready"))
        self.lbl_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #1a5fb4;")
        status_bar_layout.addWidget(self.lbl_status)
        status_bar_layout.addStretch()

        self.lbl_last_check = QLabel(f"{tr('status_last_check')} {tr('status_never')}")
        self.lbl_last_check.setStyleSheet("color: #666; font-size: 11px;")
        status_bar_layout.addWidget(self.lbl_last_check)
        layout.addLayout(status_bar_layout)

        # Sekcja listy ważnych maili
        lbl_section = QLabel(tr("section_important"))
        lbl_section.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 4px;")
        layout.addWidget(lbl_section)

        self.tbl_mails = QTableWidget(0, 4)
        self.tbl_mails.setHorizontalHeaderLabels([
            tr("col_sender"),
            tr("col_subject"),
            tr("col_reason"),
            tr("col_actions"),
        ])
        header = self.tbl_mails.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_mails.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.tbl_mails)

        # Dolny pasek przycisków
        btn_layout = QHBoxLayout()

        self.btn_check_now = QPushButton(tr("btn_check_now"))
        self.btn_check_now.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_check_now.clicked.connect(self._on_check_now)
        btn_layout.addWidget(self.btn_check_now)

        self.btn_mute = QPushButton(tr("btn_mute"))
        self.btn_mute.clicked.connect(self._toggle_mute)
        btn_layout.addWidget(self.btn_mute)

        btn_layout.addStretch()

        self.btn_settings = QPushButton(tr("btn_settings"))
        self.btn_settings.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.btn_settings.clicked.connect(self._open_settings)
        btn_layout.addWidget(self.btn_settings)

        layout.addLayout(btn_layout)
        self.setCentralWidget(central_widget)

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
        self.lbl_status.setText(tr("status_checking"))
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

    def _on_cycle_error(self, err_msg: str) -> None:
        self.btn_check_now.setEnabled(True)
        friendly = format_friendly_error(err_msg, lang=get_language())
        self.lbl_status.setText(f"Problem: {friendly}")

    def _add_important_mail(self, item: ProcessedMail) -> None:
        self.important_items.append(item)
        row = self.tbl_mails.rowCount()
        self.tbl_mails.insertRow(row)

        reason = item.analysis_reason or "; ".join(item.rule_reasons)
        self.tbl_mails.setItem(row, 0, QTableWidgetItem(item.mail.sender))
        self.tbl_mails.setItem(row, 1, QTableWidgetItem(item.mail.subject))
        self.tbl_mails.setItem(row, 2, QTableWidgetItem(reason))

        btn_listen = QPushButton(tr("btn_listen_summary"))
        btn_listen.clicked.connect(lambda _, m=item: self._listen_to_mail(m))
        self.tbl_mails.setCellWidget(row, 3, btn_listen)

    def _listen_to_mail(self, item: ProcessedMail) -> None:
        """Odtwarza streszczenie wybranego maila."""
        if not self.speaker:
            return
        lang = item.language if item.language in ("pl", "en") else get_language()
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
            self.btn_mute.setStyleSheet("background-color: #ffd8a8;")
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
            self.service.config = new_config
            save_config(new_config, self.config_path)

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

        elif isinstance(event, BacklogQuestion):
            if not self._is_muted:
                self._ask_backlog(event.items, event.count)

        elif isinstance(event, (BeepReminder, AskReminder)):
            if self.voice_dialog and not self._is_muted:
                self.voice_dialog.handle_event(event)
            elif isinstance(event, BeepReminder) and self.beeper and not self._is_muted:
                self.beeper.beep()

        elif isinstance(event, ServiceError):
            friendly = format_friendly_error(event.message, lang=get_language())
            self.lbl_status.setText(f"Problem: {friendly}")

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
