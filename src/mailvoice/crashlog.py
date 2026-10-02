"""Zapis nieobsłużonych błędów do pliku logu i czytelny komunikat zamiast cichej awarii."""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

import platformdirs

_logger = logging.getLogger("mailvoice.crash")
_fault_file = None


def log_path() -> Path:
    return Path(platformdirs.user_log_dir("mailvoice")) / "mailvoice.log"


def install(path: Path | None = None) -> Path:
    """Podpina zapis błędów do pliku. Zwraca ścieżkę logu."""
    global _fault_file
    path = path or log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(h, RotatingFileHandler) for h in _logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=500_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
    try:  # zrzut stosu przy twardej awarii (np. segfault w Qt)
        _fault_file = open(path.with_name("crash.txt"), "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(_fault_file)
    except OSError:
        pass

    def _hook(exc_type, exc, tb):
        report(exc_type, exc, tb)
        sys.__excepthook__(exc_type, exc, tb)

    def _thread_hook(args):
        report(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _hook
    threading.excepthook = _thread_hook
    return path


def report(exc_type, exc, tb) -> None:
    """Zapisuje błąd do logu i pokazuje komunikat (tylko w wątku głównym)."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    _logger.error("Nieobsłużony błąd:\n%s", text)
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("MailVoice")
            box.setText(
                "Coś poszło nie tak. Szczegóły zapisano w pliku:\n"
                f"{log_path()}\n\nMożesz spróbować ponownie."
            )
            box.setDetailedText(f"{exc_type.__name__}: {exc}")
            box.exec()
    except Exception:  # noqa: BLE001 — komunikat nie może sam wywołać kolejnego błędu
        pass
