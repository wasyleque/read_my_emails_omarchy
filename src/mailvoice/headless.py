"""Tryb headless (bez GUI) dla MailVoice i serwera mobilnego.

Uruchamiany przez:
  python -m mailvoice --headless
lub
  mailvoice-server
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Any

import platformdirs

from mailvoice import crashlog
from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AppConfig, load_config, save_config
from mailvoice.core.devices import DeviceManager
from mailvoice.core.secrets import KeyringStore, SecretStore, SecretStoreUnavailable
from mailvoice.core.service import MailService
from mailvoice.core.store import Store
from mailvoice.server.server import MobileServer

logger = logging.getLogger("mailvoice.headless")


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


def run_headless(
    argv: list[str] | None = None,
    stop_event: threading.Event | None = None,
    custom_deps: dict[str, Any] | None = None,
) -> int:
    """Uruchamia serwis pocztowy i serwer mobilny w trybie bezokienkowym."""
    parser = argparse.ArgumentParser(
        prog="mailvoice-server",
        description="Serwer bezokienkowy (headless) dla aplikacji MailVoice.",
    )
    parser.add_argument("--headless", action="store_true", help="Flaga trybu headless.")
    parser.add_argument(
        "--config", type=str, default=None, help="Ścieżka do pliku konfiguracyjnego."
    )
    parser.add_argument(
        "--data-dir", type=str, default=None, help="Katalog bazy danych i certyfikatów."
    )
    parser.add_argument("--port", type=int, default=None, help="Port serwera HTTPS.")
    parser.add_argument("--bind", type=str, default=None, help="Adres IP nasłuchu serwera.")
    parser.add_argument(
        "--tick-interval",
        type=float,
        default=2.0,
        help="Interwał sprawdzania zegara (w sekundach).",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Ścieżki konfiguracji i danych
    if args.config:
        config_file = Path(args.config)
        config_dir = config_file.parent
    else:
        config_dir = Path(platformdirs.user_config_dir("mailvoice"))
        config_file = config_dir / "config.json"

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = Path(platformdirs.user_data_dir("mailvoice"))

    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "mailvoice.db"

    # Wczytanie lub utworzenie konfiguracji
    if config_file.exists():
        config = load_config(config_file)
    else:
        config = AppConfig()
        save_config(config, config_file)

    # Nadpisanie opcji wiersza poleceń jeśli podano
    if args.port is not None:
        config.server.port = args.port
    if args.bind is not None:
        config.server.bind = args.bind

    deps = custom_deps or {}
    store: Store = deps.get("store") or Store(str(db_file))
    device_manager: DeviceManager = deps.get("device_manager") or DeviceManager(str(db_file))
    secret_store: SecretStore = deps.get("secret_store") or get_secret_store()
    ollama_client: OllamaClient = deps.get("ollama_client") or OllamaClient(config.ollama)

    service: MailService = deps.get("service") or MailService(
        config=config,
        store=store,
        secret_store=secret_store,
        ollama_client=ollama_client,
        client_factory=deps.get("client_factory"),
        clock=deps.get("clock"),
    )

    server: MobileServer | None = None
    if config.server.enabled:
        server = MobileServer(
            config=config,
            store=store,
            device_manager=device_manager,
            service=service,
            data_dir=data_dir,
        )
        service.add_listener(server.broadcast_event)
        try:
            server.start()
            logger.info("Uruchomiono serwer mobilny na %s", server.url)
        except Exception as exc:
            logger.error("Błąd startu serwera mobilnego: %s", exc)

    shutdown_event = stop_event or threading.Event()

    # Obsługa sygnałów zamknięcia (SIGINT, SIGTERM)
    def handle_signal(sig: int, _frame: Any) -> None:
        logger.info("Odebrano sygnał %s, zamykanie trybu headless...", sig)
        shutdown_event.set()

    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except (ValueError, AttributeError):
            pass

    logger.info("Tryb headless aktywny. Oczekiwanie na cykle...")

    try:
        while not shutdown_event.is_set():
            service.tick()
            shutdown_event.wait(timeout=args.tick_interval)
    finally:
        logger.info("Zatrzymywanie usług trybu headless...")
        if server is not None:
            server.stop()
        logger.info("Tryb headless zatrzymany pomyślnie.")

    return 0


def main() -> int:
    """Główna funkcja uruchamiająca skrypt mailvoice-server."""
    crashlog.install()
    try:
        return run_headless()
    except Exception:  # noqa: BLE001
        crashlog.report(*sys.exc_info())
        return 1
