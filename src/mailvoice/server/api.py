"""API REST i WebSocket dla aplikacji mobilnej MailVoice (aiohttp.web).

Zgodnie z zasadami bezpieczeństwa (SECURITY.md):
- Brak żądań wychodzących (tylko nasłuch serwera).
- Wszystkie odpowiedzi zawierają nagłówki bezpieczeństwa.
- Adresy URL w streszczeniach i tematach są zdefangowane/usunięte.
- Brak surowych treści maili i brak załączników w API.
- Identyfikatory wiadomości są nieprzewidywalnymi wartościami opaque.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiohttp import WSMsgType, web

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import (
    DeviceLimitError,
    DeviceManager,
    PairedDevice,
    PairingError,
    PairingExpiredError,
    PairingLockedError,
)
from mailvoice.core.digest import build_digest
from mailvoice.core.ignore import (
    IGNORE_MODES,
    IgnoreRule,
    is_ignored_by_config,
    rule_for_mail,
)
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.core.summarizer import filter_urls
from mailvoice.voice.dialog import VoiceCommand, classify_command

logger = logging.getLogger(__name__)


@dataclass
class ServerContext:
    """Kontekst współdzielony serwera HTTP/WebSocket."""

    config: AppConfig
    store: Store
    device_manager: DeviceManager
    service: Any = None  # MailService | None
    on_ignore: Callable[[IgnoreRule], None] | None = None  # przekazanie do wątku GUI
    on_vip: Callable[[IgnoreRule], None] | None = None  # j.w., dla reguł VIP
    # losowy klucz na każde uruchomienie serwera: identyfikatory maili są nieprzewidywalne
    server_key: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    opaque_id_map: dict[str, tuple[str, str, int, int]] = field(default_factory=dict)
    event_queues: dict[web.WebSocketResponse, asyncio.Queue] = field(default_factory=dict)
    rate_limits: dict[str, list[float]] = field(default_factory=dict)
    rate_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    digest_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    digest_cache: dict[int, tuple[float, Any]] = field(default_factory=dict)


CONTEXT_KEY: web.AppKey[ServerContext] = web.AppKey("context", ServerContext)
DEVICE_KEY: web.RequestKey[PairedDevice] = web.RequestKey("device", PairedDevice)


def get_opaque_id(ctx: ServerContext, account: str, folder: str, uidvalidity: int, uid: int) -> str:
    """Generuje bezpieczny, nieprzewidywalny identyfikator wiadomości."""
    raw = f"{account}:{folder}:{uidvalidity}:{uid}".encode("utf-8")
    oid = hmac.new(ctx.server_key, raw, hashlib.sha256).hexdigest()[:24]
    ctx.opaque_id_map[oid] = (account, folder, uidvalidity, uid)
    return oid


def get_client_ip(request: web.Request) -> str:
    """Zwraca adres IP klienta."""
    return request.remote or "unknown"


@web.middleware
async def security_headers_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Dodaje nagłówki bezpieczeństwa do każdej odpowiedzi serwera."""
    response = await handler(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Server"] = "MailVoice"
    return response


_access_log = logging.getLogger("mailvoice.crash")  # ten sam plik logu co błędy aplikacji


@web.middleware
async def access_log_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Dziennik zapytań do diagnostyki: metoda, ścieżka, kod, adres. Bez tokenów i bez treści."""
    status = 500
    try:
        response = await handler(request)
        status = response.status
        return response
    except web.HTTPException as exc:
        status = exc.status
        raise
    finally:
        # identyfikator maili w ścieżce jest nieprzewidywalny, więc bezpieczny w logu
        _access_log.info(
            "telefon: %s %s -> %s (%s)", request.method, request.path, status, request.remote
        )


@web.middleware
async def rate_limit_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Ogranicza liczbę zapytań z jednego adresu IP (ochrona przed DoS i brute-force)."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    ip = get_client_ip(request)
    now = datetime.now(timezone.utc).timestamp()

    # Osobne limity dla parowania (bardziej restrykcyjne)
    is_pair = request.path == "/v1/pair"
    window_s = 60.0
    max_requests = 5 if is_pair else 60
    key = f"{'pair:' if is_pair else 'req:'}{ip}"

    async with ctx.rate_lock:
        timestamps = [t for t in ctx.rate_limits.get(key, []) if now - t < window_s]
        if len(timestamps) >= max_requests:
            return web.json_response(
                {"error": "Zbyt wiele zapytań. Odczekaj chwilę."},
                status=429,
            )
        timestamps.append(now)
        ctx.rate_limits[key] = timestamps

    return await handler(request)


@web.middleware
async def auth_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Weryfikuje autoryzację tokenem Bearer dla wszystkich endpointów poza parowaniem."""
    # Ścieżka parowania nie wymaga wcześniejszego tokenu
    if request.path == "/v1/pair":
        return await handler(request)

    ctx: ServerContext = request.app[CONTEXT_KEY]

    token: str | None = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    # Token WYŁĄCZNIE w nagłówku: adres URL (z ?token=) trafia do logów, historii i proxy.

    if not token:
        return web.json_response(
            {"error": "Brak tokenu autoryzacji."},
            status=401,
        )

    device: PairedDevice | None = ctx.device_manager.verify_token(token)
    if not device:
        return web.json_response(
            {"error": "Nieprawidłowy lub odwołany token urządzenia."},
            status=401,
        )

    request[DEVICE_KEY] = device
    return await handler(request)


async def handle_pair(request: web.Request) -> web.Response:
    """POST /v1/pair - Parowanie nowego telefonu."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Niepoprawny format JSON."}, status=400)

    code = str(data.get("code", "")).strip()
    device_name = str(data.get("device_name", "Telefon")).strip()

    if not code:
        return web.json_response({"error": "Pole 'code' jest wymagane."}, status=400)

    try:
        max_dev = ctx.config.server.max_devices
        dev_id, token = ctx.device_manager.pair_device(
            code=code,
            device_name=device_name,
            max_devices=max_dev,
        )
        return web.json_response(
            {
                "device_id": dev_id,
                "token": token,
                "message": "Pomyślnie sparowano urządzenie.",
            }
        )
    except PairingLockedError as exc:
        return web.json_response({"error": str(exc)}, status=429)
    except PairingExpiredError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except PairingError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except DeviceLimitError as exc:
        return web.json_response({"error": str(exc)}, status=403)
    except Exception as exc:
        logger.error("Błąd parowania urządzenia: %s", exc)
        return web.json_response({"error": "Nie udało się sparować urządzenia."}, status=500)


async def handle_status(request: web.Request) -> web.Response:
    """GET /v1/status - Zwraca status programu (bez adresów e-mail)."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    last_tick_iso = None
    if ctx.service and hasattr(ctx.service, "last_tick") and ctx.service.last_tick:
        last_tick_iso = ctx.service.last_tick.isoformat()

    active_devices = ctx.device_manager.list_devices(include_revoked=False)

    return web.json_response(
        {
            "version": "0.1.0",
            "last_tick": last_tick_iso,
            "accounts_count": len(ctx.config.accounts),
            "active_devices_count": len(active_devices),
        }
    )


def _format_mail_item(ctx: ServerContext, r: MailIndexRecord) -> dict[str, Any]:
    oid = get_opaque_id(ctx, r.account, r.folder, r.uidvalidity, r.uid)
    status = ctx.store.get_seen_status(r.account, r.folder, r.uidvalidity, r.uid)
    is_suspicious = r.risk == "high"

    # W liście zwracamy zdefangowane podsumowanie lub None jeśli podejrzany
    summary = filter_urls(r.summary or "") if not is_suspicious else None
    why = filter_urls(r.why or "")
    subject = filter_urls(r.subject or "")

    return {
        "id": oid,
        "sender": r.sender,
        "subject": subject,
        "importance": r.importance or 0,
        "why": why,
        "summary": summary,
        "suspicious": is_suspicious,
        "date": r.date,
        "acknowledged": status in ("listened", "acknowledged"),
    }


async def handle_important_mails(request: web.Request) -> web.Response:
    """GET /v1/mails/important - Zwraca listę ważnych wiadomości bez treści i aktywnych linków."""
    ctx: ServerContext = request.app[CONTEXT_KEY]

    limit_str = request.query.get("limit", "20")
    try:
        limit = max(1, min(100, int(limit_str)))
    except ValueError:
        limit = 20

    records = ctx.store.get_important_indexed_records(
        min_importance=ctx.config.importance_threshold,
        limit=limit,
    )

    records = [r for r in records if not is_ignored_by_config(ctx.config, r.sender, r.subject)]
    items = [_format_mail_item(ctx, r) for r in records]
    return web.json_response({"mails": items})


async def handle_mail_summary(request: web.Request) -> web.Response:
    """GET /v1/mails/{id}/summary - Zwraca streszczenie lub ostrzeżenie o podejrzeniu."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    mail_id = request.match_info["id"]

    target = ctx.opaque_id_map.get(mail_id)
    if not target:
        return web.json_response({"error": "Wiadomość nie znaleziona."}, status=404)

    acc, folder, uidvalidity, uid = target
    record = ctx.store.get_mail_index(acc, folder, uidvalidity, uid)
    if not record:
        return web.json_response({"error": "Wiadomość nie znaleziona w indeksie."}, status=404)

    if record.risk == "high":
        return web.json_response(
            {
                "id": mail_id,
                "suspicious": True,
                "warning": "Uwaga, ta wiadomość wygląda na podejrzaną. Treść nie została pobrana.",
                "summary": None,
            }
        )

    return web.json_response(
        {
            "id": mail_id,
            "suspicious": False,
            "warning": None,
            "summary": filter_urls(record.summary or ""),
        }
    )


async def _handle_mail_rule(request: web.Request, kind: str) -> web.Response:
    """Wspólna obsługa „ignoruj” i „VIP”: tworzy regułę z maila i przekazuje ją do GUI."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    target = ctx.opaque_id_map.get(request.match_info["id"])
    if not target:
        return web.json_response({"error": "Wiadomość nie znaleziona."}, status=404)
    try:
        body = await request.json()
        mode = str(body.get("mode", "similar"))
    except (ValueError, AttributeError):
        return web.json_response({"error": "Niepoprawne żądanie."}, status=400)
    if mode not in IGNORE_MODES:
        return web.json_response({"error": "Nieznany tryb."}, status=400)
    callback = ctx.on_ignore if kind == "ignore" else ctx.on_vip
    if callback is None:
        return web.json_response({"error": "Ta funkcja jest niedostępna."}, status=503)
    record = ctx.store.get_mail_index(*target)
    if not record:
        return web.json_response({"error": "Wiadomość nie znaleziona."}, status=404)
    if kind == "vip" and (record.risk != "low" or record.risk_reasons):
        # Podrobiony nadawca nie może zostać VIP-em jednym kliknięciem (także gdy ktoś ominie UI).
        return web.json_response(
            {"error": "Nie można oznaczyć jako VIP wiadomości podejrzanej."}, status=403
        )
    rule = rule_for_mail(mode, record.sender, record.subject)
    callback(rule)
    return web.json_response({"status": "ok", "mode": mode, "rule": rule.describe()})


async def handle_mail_ignore(request: web.Request) -> web.Response:
    """POST /v1/mails/{id}/ignore {mode} - Ignoruje podobne maile (similar | sender | domain)."""
    return await _handle_mail_rule(request, "ignore")


async def handle_mail_vip(request: web.Request) -> web.Response:
    """POST /v1/mails/{id}/vip {mode} - Oznacza nadawcę/podobne maile jako VIP (jak „ignoruj”)."""
    return await _handle_mail_rule(request, "vip")


async def handle_mail_ack(request: web.Request) -> web.Response:
    """POST /v1/mails/{id}/ack - Oznacza wiadomość lokalnie jako wysłuchaną."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    mail_id = request.match_info["id"]

    target = ctx.opaque_id_map.get(mail_id)
    if not target:
        return web.json_response({"error": "Wiadomość nie znaleziona."}, status=404)

    acc, folder, uidvalidity, uid = target
    record = ctx.store.get_mail_index(acc, folder, uidvalidity, uid)
    msg_id = record.message_id if record else None

    ctx.store.mark_seen(
        account=acc,
        folder=folder,
        uidvalidity=uidvalidity,
        uid=uid,
        message_id=msg_id,
        status="listened",
        importance=record.importance if record else None,
    )

    return web.json_response(
        {
            "status": "ok",
            "message": "Wiadomość oznaczona jako wysłuchana.",
        }
    )


_ACTIONABLE = ("oczekuje_na_mnie", "oczekuje_na_innych")
_DIGEST_TTL_S = 120.0


def _compute_digest(ctx: ServerContext, days: int):
    """Liczy podsumowanie w wątku roboczym; krótki budżet modelu = szybka odpowiedź dla telefonu."""
    if ctx.service and hasattr(ctx.service, "request_digest"):
        return ctx.service.request_digest(
            days=days, emit=False, llm_budget=3, llm_deadline_s=8.0, llm_timeout_s=6.0
        )
    from mailvoice.core.analyzer import OllamaClient

    client = getattr(ctx.service, "ollama_client", None) or OllamaClient(ctx.config.ollama)
    return build_digest(ctx.store, client, ctx.config, llm_budget=3, llm_deadline_s=8.0)


async def handle_digest(request: web.Request) -> web.Response:
    """GET /v1/digest?days=&limit=&all= - Podsumowanie tematów (domyślnie tylko sprawy otwarte).

    Zwraca najwyżej `limit` tematów (domyślnie 60) w KAŻDEJ grupie statusu osobno — inaczej
    wiele spraw „czeka na mnie” wypychałoby z odpowiedzi całą grupę „czeka na innych”.
    Bez `all=1` pomija tematy „zamknięte” i „informacyjne” (zwykle najliczniejsze),
    ale podaje ich liczbę w `counts`.
    """
    ctx: ServerContext = request.app[CONTEXT_KEY]
    try:
        days = max(1, min(365, int(request.query.get("days", ctx.config.digest_days))))
    except ValueError:
        days = ctx.config.digest_days
    try:
        limit = max(1, min(200, int(request.query.get("limit", "60"))))
    except ValueError:
        limit = 60
    include_all = request.query.get("all") == "1"

    now = time.monotonic()
    async with ctx.digest_lock:  # jedno liczenie naraz; kolejne zapytania dostają wynik z pamięci
        cached = ctx.digest_cache.get(days)
        if cached and now - cached[0] < _DIGEST_TTL_S:
            digest = cached[1]
        else:
            digest = await asyncio.get_running_loop().run_in_executor(
                None, _compute_digest, ctx, days
            )
            ctx.digest_cache[days] = (time.monotonic(), digest)

    counts: dict[str, int] = {}
    for t in digest.topics:
        counts[t.status] = counts.get(t.status, 0) + 1
    chosen: list = []
    per_status: dict[str, int] = {}
    for t in digest.topics:  # kolejność z serwera (VIP, ważność, świeżość) zostaje w obrębie grupy
        if not (include_all or t.status in _ACTIONABLE):
            continue
        if per_status.get(t.status, 0) < limit:
            per_status[t.status] = per_status.get(t.status, 0) + 1
            chosen.append(t)

    topics_data = [
        {
            "title": filter_urls(t.title),
            "status": t.status,
            "why": filter_urls(t.why),
            "importance": t.importance,
            "mail_count": t.mail_count,
            "vip": t.vip,
            "last_activity": t.last_activity.isoformat() if t.last_activity else None,
            "who_to_whom": t.who_to_whom,
        }
        for t in chosen
    ]
    return web.json_response(
        {
            "period": digest.period,
            "topics": topics_data,
            "counts": counts,
            "total": len(digest.topics),
            "shown": len(topics_data),
        }
    )


async def handle_voice_command(request: web.Request) -> web.Response:
    """POST /v1/voice/command - Interpretuje komendę głosową przesłaną z telefonu."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Niepoprawny format JSON."}, status=400)

    text = str(data.get("text", "")).strip()
    lang = str(data.get("lang", "pl")).lower()
    if lang not in ("pl", "en"):
        lang = "pl"

    cmd = classify_command(text)

    # Odpowiedzi głosowe / tekstowe w wybranym języku
    responses_pl = {
        VoiceCommand.NEXT: ("next", "Przechodzę do kolejnej wiadomości."),
        VoiceCommand.REPEAT: ("repeat", "Powtarzam wiadomość."),
        VoiceCommand.SKIP: ("skip", "Pomijam wiadomość."),
        VoiceCommand.STOP: ("stop", "Zatrzymano."),
        VoiceCommand.YES: ("yes", "Dobrze, czytam wiadomości."),
        VoiceCommand.NO: ("no", "Dobrze, przypomnę później."),
        VoiceCommand.LOUDER: ("louder", "Zwiększono głośność."),
        VoiceCommand.QUIETER: ("quieter", "Zmniejszono głośność."),
        VoiceCommand.DIGEST: ("digest", "Generuję podsumowanie tematów."),
        VoiceCommand.CONTACT: ("contact", "Wyszukuję kontakt."),
        VoiceCommand.SEARCH: ("search", "Wyszukuję wiadomości."),
        VoiceCommand.UNKNOWN: ("unknown", "Nie rozumiem polecenia."),
    }

    responses_en = {
        VoiceCommand.NEXT: ("next", "Moving to next message."),
        VoiceCommand.REPEAT: ("repeat", "Repeating message."),
        VoiceCommand.SKIP: ("skip", "Skipping message."),
        VoiceCommand.STOP: ("stop", "Stopped."),
        VoiceCommand.YES: ("yes", "Alright, reading messages."),
        VoiceCommand.NO: ("no", "Alright, will remind later."),
        VoiceCommand.LOUDER: ("louder", "Volume increased."),
        VoiceCommand.QUIETER: ("quieter", "Volume decreased."),
        VoiceCommand.DIGEST: ("digest", "Generating topic digest."),
        VoiceCommand.CONTACT: ("contact", "Looking up contact."),
        VoiceCommand.SEARCH: ("search", "Searching emails."),
        VoiceCommand.UNKNOWN: ("unknown", "Command not recognized."),
    }

    resp_map = responses_pl if lang == "pl" else responses_en
    action, reply_text = resp_map.get(cmd, ("unknown", "Nie rozumiem polecenia."))

    return web.json_response(
        {
            "action": action,
            "reply_text": reply_text,
        }
    )


async def handle_disconnect_self(request: web.Request) -> web.Response:
    """DELETE /v1/devices/self - Odłączenie bieżącego urządzenia."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    device: PairedDevice = request[DEVICE_KEY]

    ctx.device_manager.revoke_device(device.id)
    return web.json_response(
        {
            "status": "ok",
            "message": "Urządzenie zostało pomyślnie odłączone.",
        }
    )


async def handle_events_websocket(request: web.Request) -> web.WebSocketResponse:
    """GET /v1/events - Strumień zdarzeń w czasie rzeczywistym przez WebSocket."""
    ctx: ServerContext = request.app[CONTEXT_KEY]
    ws = web.WebSocketResponse(heartbeat=25.0)
    await ws.prepare(request)

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    ctx.event_queues[ws] = queue

    try:
        # Pętla nasłuchu na kolejce i wysyłania do klienta
        while not ws.closed:
            # Równolegle czekamy na wiadomość z kolejki lub zamknięcie klienta
            get_task = asyncio.create_task(queue.get())
            receive_task = asyncio.create_task(ws.receive())

            done, pending = await asyncio.wait(
                [get_task, receive_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if receive_task in done:
                msg = receive_task.result()
                if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.ERROR):
                    break

            if get_task in done:
                event_data = get_task.result()
                await ws.send_json(event_data)
    except Exception as exc:
        logger.debug("Zakończenie połączenia WebSocket: %s", exc)
    finally:
        ctx.event_queues.pop(ws, None)
        if not ws.closed:
            await ws.close()

    return ws


def create_app(context: ServerContext) -> web.Application:
    """Tworzy i konfiguruje instancję aplikacji aiohttp.web."""
    app = web.Application(
        client_max_size=64 * 1024,  # Limit rozmiaru żądania: 64 KB
        middlewares=[
            access_log_middleware,
            security_headers_middleware,
            rate_limit_middleware,
            auth_middleware,
        ],
    )
    app[CONTEXT_KEY] = context

    # Trasy API
    app.router.add_post("/v1/pair", handle_pair)
    app.router.add_get("/v1/status", handle_status)
    app.router.add_get("/v1/mails/important", handle_important_mails)
    app.router.add_get("/v1/mails/{id}/summary", handle_mail_summary)
    app.router.add_post("/v1/mails/{id}/ack", handle_mail_ack)
    app.router.add_post("/v1/mails/{id}/ignore", handle_mail_ignore)
    app.router.add_post("/v1/mails/{id}/vip", handle_mail_vip)
    app.router.add_get("/v1/digest", handle_digest)
    app.router.add_post("/v1/voice/command", handle_voice_command)
    app.router.add_delete("/v1/devices/self", handle_disconnect_self)
    app.router.add_get("/v1/events", handle_events_websocket)

    return app
