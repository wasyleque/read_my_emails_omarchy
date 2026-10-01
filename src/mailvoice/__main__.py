"""Punkt wejścia do aplikacji MailVoice."""

import sys

from PySide6.QtWidgets import QApplication

from mailvoice.ui.main_window import MainWindow


def main() -> int:
    """Uruchamia aplikację okienkową MailVoice."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
