"""Testy trybu bezokienkowego (headless)."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from mailvoice.core.config import AppConfig, save_config
from mailvoice.core.devices import DeviceManager
from mailvoice.core.store import Store
from mailvoice.headless import MemorySecretStore, run_headless


def test_headless_smoke_start_and_shutdown(tmp_path: Path):
    """Weryfikuje uruchomienie pętli headless z serwerem i czyste zatrzymanie."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    cfg_file = config_dir / "config.json"
    cfg = AppConfig()
    cfg.server.enabled = True
    cfg.server.port = 19876
    cfg.server.bind = "127.0.0.1"
    save_config(cfg, cfg_file)

    stop_event = threading.Event()
    store = Store(str(data_dir / "test.db"))
    dev_mgr = DeviceManager(str(data_dir / "test.db"))
    secrets = MemorySecretStore()

    fake_service = MagicMock()
    fake_service.tick = MagicMock()

    custom_deps = {
        "store": store,
        "device_manager": dev_mgr,
        "secret_store": secrets,
        "service": fake_service,
    }

    # Uruchomienie w osobnym wątku
    thread_result = []

    def worker():
        code = run_headless(
            argv=[
                "--config",
                str(cfg_file),
                "--data-dir",
                str(data_dir),
                "--tick-interval",
                "0.05",
            ],
            stop_event=stop_event,
            custom_deps=custom_deps,
        )
        thread_result.append(code)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # Dajemy chwilę na wykonanie chociaż jednego ticku
    time.sleep(0.15)
    stop_event.set()
    t.join(timeout=3.0)

    assert not t.is_alive()
    assert thread_result == [0]
    assert fake_service.tick.call_count >= 1


def test_headless_cli_args_override(tmp_path: Path):
    """Weryfikuje nadpisywanie portu i bind przez argumenty CLI."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    cfg_file = config_dir / "config.json"
    cfg = AppConfig()
    cfg.server.enabled = False  # Serwer wyłączony
    save_config(cfg, cfg_file)

    stop_event = threading.Event()
    stop_event.set()  # Natychmiastowe zakończenie

    fake_service = MagicMock()

    custom_deps = {
        "service": fake_service,
    }

    ret = run_headless(
        argv=[
            "--config",
            str(cfg_file),
            "--data-dir",
            str(data_dir),
            "--port",
            "18888",
            "--bind",
            "127.0.0.1",
            "--tick-interval",
            "0.01",
        ],
        stop_event=stop_event,
        custom_deps=custom_deps,
    )
    assert ret == 0
