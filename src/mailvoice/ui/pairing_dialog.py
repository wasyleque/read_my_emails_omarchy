"""Okno dialogowe parowania telefonu z kodem QR i odliczaniem czasu."""

from __future__ import annotations

import io
from pathlib import Path

import segno
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.devices import DeviceManager, PairingSession
from mailvoice.core.tls import detect_lan_ip, get_or_create_tls_credentials
from mailvoice.ui import theme
from mailvoice.ui.i18n import tr


class PairingDialog(QDialog):
    """Okno dialogowe wyświetlające kod QR i kod tekstowy do sparowania telefonu."""

    def __init__(
        self,
        device_manager: DeviceManager,
        port: int,
        data_dir: Path,
        bind_host: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.device_manager = device_manager
        self.port = port
        self.data_dir = data_dir
        self.bind_host = bind_host
        self.remaining_seconds = 120

        self.setWindowTitle(tr("pair_dialog_title"))
        self.setFixedSize(420, 520)

        # Inicjalizacja sesji parowania w bazie
        self.session: PairingSession = self.device_manager.start_pairing_session()

        self._init_ui()
        self._init_timer()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Instrukcja
        self.lbl_instructions = QLabel(tr("pair_dialog_instructions"))
        self.lbl_instructions.setWordWrap(True)
        self.lbl_instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_instructions.setStyleSheet(f"color: {theme.c('text')}; font-size: 13px;")
        layout.addWidget(self.lbl_instructions)

        # Wygenerowanie kodu QR w pamięci RAM
        lan_ip = (
            self.bind_host
            if (self.bind_host and self.bind_host != "0.0.0.0")
            else (detect_lan_ip() or "127.0.0.1")
        )
        creds = get_or_create_tls_credentials(self.data_dir)
        qr_url = (
            f"mailvoice://pair?host={lan_ip}&port={self.port}"
            f"&code={self.session.code}&fp={creds.fingerprint}&v=1"
        )

        qr = segno.make(qr_url)
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=5, border=2)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue(), "PNG")

        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setPixmap(pixmap)
        layout.addWidget(self.lbl_qr)

        # Alternatywny kod tekstowy do przepisania
        code_box = QVBoxLayout()
        lbl_alt = QLabel(tr("pair_code_alt_label"))
        lbl_alt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_alt.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        code_box.addWidget(lbl_alt)

        self.lbl_code = QLabel(self.session.code)
        self.lbl_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_code.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {theme.c('accent')}; letter-spacing: 4px;"
        )
        code_box.addWidget(self.lbl_code)
        layout.addLayout(code_box)

        # Odliczanie czasu ważności kodu (120 s)
        self.lbl_timer = QLabel(tr("pair_time_remaining", seconds=self.remaining_seconds))
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_timer.setStyleSheet(f"color: {theme.c('muted')}; font-size: 12px;")
        layout.addWidget(self.lbl_timer)

        layout.addStretch()

        # Przycisk Zamknij
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton(tr("btn_close"))
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _init_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

    def _on_tick(self) -> None:
        self.remaining_seconds -= 1
        if self.remaining_seconds > 0:
            self.lbl_timer.setText(tr("pair_time_remaining", seconds=self.remaining_seconds))
        else:
            self.timer.stop()
            self.lbl_timer.setText(tr("pair_expired"))
            self.lbl_timer.setStyleSheet(f"color: {theme.c('warn')}; font-weight: bold;")
            self.lbl_qr.setEnabled(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        super().closeEvent(event)
