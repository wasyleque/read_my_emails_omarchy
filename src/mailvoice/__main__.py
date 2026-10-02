"""Punkt wejścia do aplikacji MailVoice."""

import sys
from pathlib import Path

import platformdirs
from PySide6.QtWidgets import QApplication

from mailvoice import crashlog
from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import load_config, save_config
from mailvoice.core.instance import acquire_instance_lock
from mailvoice.core.migrate import migrate_server_state
from mailvoice.core.secrets import KeyringStore, SecretStore, SecretStoreUnavailable
from mailvoice.core.service import MailService
from mailvoice.core.store import Store
from mailvoice.ui.i18n import set_language
from mailvoice.ui.main_window import MainWindow
from mailvoice.ui.wizard import SetupWizard
from mailvoice.voice.beeper import SounddeviceBeeper
from mailvoice.voice.dialog import VoiceDialog
from mailvoice.voice.stt import WhisperListener
from mailvoice.voice.tts import PiperSpeaker


class MemorySecretStore:
    """Zapasowy magazyn sekretów w pamięci w przypadku braku systemowego pęku kluczy."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self._secrets.get(account)

    def set(self, account: str, secret: str) -> None:
        self._secrets[account] = secret

    def delete(self, account: str) -> None:
        self._secrets.pop(account, None)


def get_secret_store() -> SecretStore:
    """Inicjalizuje domyślny magazyn sekretów (systemowy pęk kluczy lub pamięć)."""
    try:
        return KeyringStore()
    except SecretStoreUnavailable:
        return MemorySecretStore()


def main() -> int:
    """Główna funkcja uruchamiająca aplikację MailVoice (z zapisem błędów do logu)."""
    crashlog.install()
    lock = acquire_instance_lock()
    if lock is None:
        _report_already_running("--headless" in sys.argv)
        return 1
    if "--data-dir" not in sys.argv:
        migrate_server_state(
            Path(platformdirs.user_config_dir("mailvoice")),
            Path(platformdirs.user_data_dir("mailvoice")),
        )
    if "--headless" in sys.argv:
        from mailvoice.headless import run_headless

        return run_headless()

    try:
        return _run()
    except Exception:  # noqa: BLE001 — błąd startu ma trafić do logu i do okna
        crashlog.report(*sys.exc_info())
        return 1


def _report_already_running(headless: bool) -> None:
    message = (
        "MailVoice już działa. Poszukaj jego okna lub ikony w zasobniku systemowym "
        "(drugie uruchomienie dublowałoby powiadomienia)."
    )
    print(message, file=sys.stderr)
    if headless:
        return
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(None, "MailVoice", message)
        del app
    except Exception:  # noqa: BLE001 — komunikat nie może sam zawieść
        pass


def _run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MailVoice")

    config_dir = Path(platformdirs.user_config_dir("mailvoice"))
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"

    data_dir = Path(platformdirs.user_data_dir("mailvoice"))
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "mailvoice.db"

    secret_store = get_secret_store()

    # Pierwsze uruchomienie — brak pliku konfiguracyjnego
    if not config_file.exists():
        wizard = SetupWizard(secret_store=secret_store)
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            # Użytkownik zamknął kreator bez zakończenia
            return 0
        config = wizard.get_app_config()
        save_config(config, config_file)
    else:
        config = load_config(config_file)

    set_language(config.language)

    # Inicjalizacja rdzenia i komponentów głosowych
    store = Store(str(db_file))
    ollama_client = OllamaClient(config.ollama)
    service = MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=ollama_client,
    )

    speaker = PiperSpeaker()
    listener = WhisperListener()
    listener.preload()  # model Whisper ładuje się w tle, nie przy pierwszym pytaniu
    beeper = SounddeviceBeeper()
    dialog = VoiceDialog(speaker=speaker, listener=listener, service=service)

    # Uruchomienie okna głównego
    window = MainWindow(
        service=service,
        config_path=config_file,
        data_dir=data_dir,
        speaker=speaker,
        beeper=beeper,
        voice_dialog=dialog,
    )
    dialog.on_problem = window.show_voice_problem
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
