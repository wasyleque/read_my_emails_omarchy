"""Zarządzanie cyklem życia serwera mobilnego MailVoice oraz mostkiem zdarzeń."""

from __future__ import annotations

import asyncio
import logging
import ssl
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web
from platformdirs import user_data_dir

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.core.service import (
    AskReminder,
    BacklogQuestion,
    BeepReminder,
    Event,
    NewImportant,
    SuspiciousMail,
)
from mailvoice.core.store import Store
from mailvoice.core.summarizer import filter_urls
from mailvoice.core.tls import TlsCredentials, detect_lan_ip, get_or_create_server_tls
from mailvoice.server.api import ServerContext, create_app, get_opaque_id

logger = logging.getLogger(__name__)


class MobileServer:
    """Serwer HTTPS/WebSocket dla aplikacji mobilnej MailVoice."""

    def __init__(
        self,
        config: AppConfig,
        store: Store,
        device_manager: DeviceManager,
        service: Any = None,
        data_dir: Path | None = None,
        on_ignore: Callable[[Any], None] | None = None,
        on_vip: Callable[[Any], None] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.device_manager = device_manager
        self.service = service
        self.data_dir = data_dir or Path(user_data_dir("mailvoice", "mailvoice"))

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._is_running = False
        self._start_event = threading.Event()

        # Wyznaczenie adresu IP nasłuchu
        configured_bind = self.config.server.bind.strip()
        self.bind_host = configured_bind if configured_bind else detect_lan_ip()
        self.port = self.config.server.port

        # Inicjalizacja poświadczeń TLS
        self.tls_credentials: TlsCredentials = get_or_create_server_tls(
            data_dir=self.data_dir,
            lan_ip=self.bind_host if self.bind_host != "0.0.0.0" else None,
        )

        self.context = ServerContext(
            config=self.config,
            store=self.store,
            device_manager=self.device_manager,
            service=self.service,
            on_ignore=on_ignore,
            on_vip=on_vip,
        )

    def update_config(self, config) -> None:
        """Podmienia konfigurację (np. po zapisie ustawień lub dodaniu reguły ignorowania)."""
        self.config = config
        self.context.config = config

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def url(self) -> str:
        return f"https://{self.bind_host}:{self.port}"

    @property
    def fingerprint(self) -> str:
        return self.tls_credentials.fingerprint

    def start(self, timeout_s: float = 5.0) -> None:
        """Uruchamia serwer w osobnym wątku roboczym z własną pętlą zdarzeń asyncio."""
        if self._is_running:
            return

        self._start_event.clear()
        self._thread = threading.Thread(
            target=self._run_server_thread,
            daemon=True,
            name="MailVoiceServerThread",
        )
        self._thread.start()

        started = self._start_event.wait(timeout=timeout_s)
        if not started or not self._is_running:
            raise RuntimeError(f"Nie udało się uruchomić serwera na {self.url}")

    def _run_server_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._start_async())
            self._is_running = True
            self._start_event.set()
            self._loop.run_forever()
        except Exception as exc:
            logger.error("Błąd wątku serwera: %s", exc)
            self._start_event.set()
        finally:
            if self._loop and not self._loop.is_closed():
                try:
                    self._loop.run_until_complete(self._stop_async())
                except Exception:
                    pass
                self._loop.close()
            self._is_running = False

    async def _start_async(self) -> None:
        app = create_app(self.context)
        self._runner = web.AppRunner(app)
        await self._runner.setup()

        # Konfiguracja SSLContext dla HTTPS
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(
            certfile=str(self.tls_credentials.cert_path),
            keyfile=str(self.tls_credentials.key_path),
        )

        self._site = web.TCPSite(
            self._runner,
            host=self.bind_host,
            port=self.port,
            ssl_context=ssl_ctx,
        )
        await self._site.start()
        logger.info("Serwer MailVoice nasłuchuje na %s", self.url)

    async def _stop_async(self) -> None:
        # Zamknięcie wszystkich aktywnych WebSocketów
        for ws in list(self.context.event_queues.keys()):
            try:
                await ws.close()
            except Exception:
                pass
        self.context.event_queues.clear()

        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    def stop(self, timeout_s: float = 3.0) -> None:
        """Czysto zatrzymuje serwer i jego pętlę zdarzeń."""
        if not self._is_running or not self._loop:
            return

        self._is_running = False
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=timeout_s)
            self._thread = None
        self._loop = None

    def connected_phones(self) -> int:
        """Liczba telefonów z aktywnym połączeniem WebSocket (bezpieczne do odczytu z wątku GUI)."""
        return len(self.context.event_queues)

    def broadcast_event(self, event: Event) -> None:
        """Bezpiecznie przekazuje zdarzenie z wątku MailService do połączonych telefonów."""
        if not self._is_running or not self._loop or self._loop.is_closed():
            return

        payload: dict[str, Any] | None = None
        now_iso = datetime.now(timezone.utc).isoformat()

        if isinstance(event, NewImportant):
            mails_data = []
            mails = getattr(event, "items", getattr(event, "mails", []))
            for m in mails:
                oid = get_opaque_id(self.context, m.account, m.folder, m.uidvalidity, m.uid)
                mails_data.append(
                    {
                        "id": oid,
                        "sender": m.mail.sender,
                        "subject": filter_urls(m.mail.subject),
                        "importance": m.final_importance,
                        "why": filter_urls(m.analysis_reason),
                        "date": m.mail.date.isoformat() if m.mail.date else None,
                        "suspicious": False,
                    }
                )
            payload = {
                "type": "NewImportant",
                "timestamp": now_iso,
                "data": {"mails": mails_data},
            }

        elif isinstance(event, SuspiciousMail):
            m = event.mail
            oid = get_opaque_id(self.context, m.account, m.folder, m.uidvalidity, m.uid)
            mail_data = {
                "id": oid,
                "sender": m.mail.sender,
                "subject": filter_urls(m.mail.subject),
                "importance": m.final_importance,
                "why": filter_urls(m.analysis_reason),
                "date": m.mail.date.isoformat() if m.mail.date else None,
                "suspicious": True,
                "reasons": list(event.reasons),
            }
            payload = {
                "type": "SuspiciousMail",
                "timestamp": now_iso,
                "data": {"mail": mail_data},
            }

        elif isinstance(event, BacklogQuestion):
            payload = {
                "type": "BacklogQuestion",
                "timestamp": now_iso,
                "data": {"count": event.count},
            }

        elif isinstance(event, BeepReminder):
            payload = {
                "type": "BeepReminder",
                "timestamp": now_iso,
                "data": {"count": event.count},
            }

        elif isinstance(event, AskReminder):
            payload = {
                "type": "AskReminder",
                "timestamp": now_iso,
                "data": {"count": event.count},
            }

        if payload:
            self._loop.call_soon_threadsafe(self._distribute_event, payload)

    def _distribute_event(self, payload: dict[str, Any]) -> None:
        """Rozsyła zdarzenie do kolejek aktywnych klientów WebSocket."""
        for ws, queue in list(self.context.event_queues.items()):
            if ws.closed:
                continue
            try:
                # Jeśli kolejka klienta jest pełna (np. wolne łącze), odrzucamy najstarsze
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(payload)
            except Exception as exc:
                logger.debug("Błąd dodawania do kolejki WebSocket: %s", exc)
