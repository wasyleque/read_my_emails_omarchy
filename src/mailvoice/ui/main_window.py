"""Główne okno aplikacji MailVoice."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    """Główne okno interfejsu użytkownika."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MailVoice")
        self.resize(600, 400)
        self._init_ui()

    def _init_ui(self) -> None:
        """Inicjalizacja widżetów okna głównego."""
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        status_label = QLabel("MailVoice — Asystent głosowy poczty", central_widget)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status_label)

        self.setCentralWidget(central_widget)
