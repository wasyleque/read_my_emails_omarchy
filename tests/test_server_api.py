"""Testy endpointów API serwera mobilnego (aiohttp.test_utils)."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import ProcessedMail
from mailvoice.core.service import NewImportant
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.server.api import ServerContext, create_app
from mailvoice.server.server import MobileServer


@pytest.fixture
def server_context(tmp_path: Path):
    cfg = AppConfig()
    store = Store(tmp_path / "test_store.db")
    dev_mgr = DeviceManager(tmp_path / "test_devices.db")
    return ServerContext(config=cfg, store=store, device_manager=dev_mgr)


@pytest.mark.anyio
async def test_server_pairing_flow_and_auth(server_context):
    """Weryfikuje pełną ścieżkę parowania urządzenia i autoryzacji tokenem."""
    app = create_app(server_context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # 1. Próba parowania bez aktywnej sesji
        resp = await client.post("/v1/pair", json={"code": "123456", "device_name": "Poco F4"})
        assert resp.status == 400

        # 2. Utworzenie aktywnej sesji parowania
        session = server_context.device_manager.start_pairing_session()

        # 3. Próba z błędnym kodem
        resp = await client.post("/v1/pair", json={"code": "BLEDNY", "device_name": "Poco F4"})
        assert resp.status == 400

        # 4. Poprawne parowanie
        resp = await client.post("/v1/pair", json={"code": session.code, "device_name": "Poco F4"})
        assert resp.status == 200
        pair_data = await resp.json()
        assert "token" in pair_data
        assert "device_id" in pair_data
        token = pair_data["token"]

        # 5. Dostęp do chronionego endpointu ze świeżym tokenem
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/v1/status", headers=headers)
        assert resp.status == 200
        status_data = await resp.json()
        assert status_data["version"] == "0.1.0"
        assert status_data["active_devices_count"] == 1

        # Sprawdzenie nagłówków bezpieczeństwa
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "default-src 'none'" in resp.headers.get("Content-Security-Policy", "")

        # 6. Dostęp z niepoprawnym tokenem -> 401
        bad_headers = {"Authorization": "Bearer niepoprawny_token_123456"}
        resp = await client.get("/v1/status", headers=bad_headers)
        assert resp.status == 401

        # 7. Dostęp bez nagłówka Authorization -> 401
        resp = await client.get("/v1/status")
        assert resp.status == 401

    finally:
        await client.close()


@pytest.mark.anyio
async def test_server_important_mails_and_summary_isolation(server_context):
    """Weryfikuje brak surowych treści, filtr linków i blokadę streszczeń podejrzanych maili."""
    store = server_context.store

    # Zapis dwóch wiadomości: jedna zwykła z URL-em, druga oznaczona jako podejrzana (phishing)
    now_iso = datetime.now(timezone.utc).isoformat()
    store.save_mail_index(
        MailIndexRecord(
            account="jan@firma.pl",
            folder="INBOX",
            uidvalidity=1,
            uid=10,
            message_id="<safe@firma.pl>",
            thread_key="thread_safe",
            date=now_iso,
            sender="klient@firma.pl",
            recipients="jan@firma.pl",
            subject="Oferta i link http://evil-tracker.com/track",
            importance=9,
            why="Ważna oferta handlowa",
            summary="Szczegóły oferty na stronie https://firma.pl/oferta dla Ciebie.",
            direction="in",
            risk="low",
            risk_reasons="",
        )
    )

    store.save_mail_index(
        MailIndexRecord(
            account="jan@firma.pl",
            folder="INBOX",
            uidvalidity=1,
            uid=11,
            message_id="<phish@hacker.xyz>",
            thread_key="thread_phish",
            date=now_iso,
            sender="bank@bezpieczny.com",
            recipients="jan@firma.pl",
            subject="Twoje konto zablokowane",
            importance=8,
            why="Presja czasu i fałszywy link",
            summary="Niebezpieczna treść z linkiem do kradzieży hasła",
            direction="in",
            risk="high",
            risk_reasons="SPF fail",
        )
    )

    # Parowanie urządzenia i uzyskanie tokenu
    session = server_context.device_manager.start_pairing_session()
    _, token = server_context.device_manager.pair_device(session.code, "Tester")
    headers = {"Authorization": f"Bearer {token}"}

    app = create_app(server_context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # 1. Pobranie listy ważnych wiadomości
        resp = await client.get("/v1/mails/important", headers=headers)
        assert resp.status == 200
        data = await resp.json()
        mails = data["mails"]
        assert len(mails) == 2

        safe_mail = next(m for m in mails if not m["suspicious"])
        phish_mail = next(m for m in mails if m["suspicious"])

        # URL w temacie i podsumowaniu bezpiecznego maila musi być zdefangowany
        assert "http://evil-tracker.com" not in safe_mail["subject"]
        assert "[link pominięty]" in safe_mail["subject"]
        assert "https://firma.pl/oferta" not in safe_mail["summary"]
        assert "[link pominięty]" in safe_mail["summary"]
        assert safe_mail["acknowledged"] is False

        # Podejrzany mail w liście nie zawiera żadnego streszczenia
        assert phish_mail["summary"] is None
        assert phish_mail["suspicious"] is True

        # Identyfikatory są nieprzewidywalnymi wartościami opaque
        assert len(safe_mail["id"]) == 24
        assert len(phish_mail["id"]) == 24

        # 2. Pobranie streszczenia dla bezpiecznego maila
        resp = await client.get(f"/v1/mails/{safe_mail['id']}/summary", headers=headers)
        assert resp.status == 200
        summary_data = await resp.json()
        assert summary_data["suspicious"] is False
        assert "[link pominięty]" in summary_data["summary"]

        # 3. Pobranie streszczenia dla podejrzanego maila -> tylko ostrzeżenie, brak streszczenia
        resp = await client.get(f"/v1/mails/{phish_mail['id']}/summary", headers=headers)
        assert resp.status == 200
        phish_summary_data = await resp.json()
        assert phish_summary_data["suspicious"] is True
        assert phish_summary_data["summary"] is None
        assert "podejrzan" in phish_summary_data["warning"].lower()

        # 4. Potwierdzenie odsłuchania (ACK)
        resp = await client.post(f"/v1/mails/{safe_mail['id']}/ack", headers=headers)
        assert resp.status == 200

        # Po ACK mail ma status acknowledged=True
        resp = await client.get("/v1/mails/important", headers=headers)
        data = await resp.json()
        updated_safe = next(m for m in data["mails"] if m["id"] == safe_mail["id"])
        assert updated_safe["acknowledged"] is True

    finally:
        await client.close()


@pytest.mark.anyio
async def test_server_voice_command_mapping(server_context):
    """Weryfikuje interpretację komend głosowych telefonu (PL i EN)."""
    session = server_context.device_manager.start_pairing_session()
    _, token = server_context.device_manager.pair_device(session.code, "VoiceTester")
    headers = {"Authorization": f"Bearer {token}"}

    app = create_app(server_context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # PL: następny
        resp = await client.post(
            "/v1/voice/command",
            json={"text": "następny mail", "lang": "pl"},
            headers=headers,
        )
        assert resp.status == 200
        res = await resp.json()
        assert res["action"] == "next"
        assert "kolejnej" in res["reply_text"]

        # PL: stop
        resp = await client.post(
            "/v1/voice/command",
            json={"text": "zatrzymaj", "lang": "pl"},
            headers=headers,
        )
        res = await resp.json()
        assert res["action"] == "stop"

        # PL: powtórz
        resp = await client.post(
            "/v1/voice/command",
            json={"text": "powtórz ten mail", "lang": "pl"},
            headers=headers,
        )
        res = await resp.json()
        assert res["action"] == "repeat"

        # PL: czytaj
        resp = await client.post(
            "/v1/voice/command",
            json={"text": "czytaj", "lang": "pl"},
            headers=headers,
        )
        res = await resp.json()
        assert res["action"] == "yes"

        # EN: skip
        resp = await client.post(
            "/v1/voice/command",
            json={"text": "skip this", "lang": "en"},
            headers=headers,
        )
        res = await resp.json()
        assert res["action"] == "skip"
        assert "Skipping" in res["reply_text"]

        # EN: read
        resp = await client.post(
            "/v1/voice/command",
            json={"text": "read it", "lang": "en"},
            headers=headers,
        )
        res = await resp.json()
        assert res["action"] == "yes"

    finally:
        await client.close()


@pytest.mark.anyio
async def test_server_device_revocation_self(server_context):
    """Weryfikuje odłączenie własnego urządzenia przez DELETE /v1/devices/self."""
    session = server_context.device_manager.start_pairing_session()
    _, token = server_context.device_manager.pair_device(session.code, "Telefon do usunięcia")
    headers = {"Authorization": f"Bearer {token}"}

    app = create_app(server_context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # Odłączenie
        resp = await client.delete("/v1/devices/self", headers=headers)
        assert resp.status == 200

        # Kolejne żądanie z tym samym tokenem musi zwrócić 401
        resp = await client.get("/v1/status", headers=headers)
        assert resp.status == 401

    finally:
        await client.close()


@pytest.mark.anyio
async def test_server_websocket_events_stream(server_context, tmp_path: Path):
    """Weryfikuje odbiór zdarzeń w czasie rzeczywistym przez WebSocket."""
    from mailvoice.core.scheduler import NotificationAction

    server = MobileServer(
        config=server_context.config,
        store=server_context.store,
        device_manager=server_context.device_manager,
        data_dir=tmp_path,
    )

    session = server_context.device_manager.start_pairing_session()
    _, token = server_context.device_manager.pair_device(session.code, "WsTester")

    app = create_app(server.context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # Połączenie WebSocket z tokenem w nagłówku Authorization
        ws = await client.ws_connect("/v1/events", headers={"Authorization": f"Bearer {token}"})
        assert not ws.closed

        # Przygotowanie i wysłanie zdarzenia
        parsed = ParsedMail(
            message_id="<ws_mail@test.pl>",
            sender="szef@firma.pl",
            subject="Pilne zebranie",
            date=datetime.now(timezone.utc),
            in_reply_to=None,
            references=(),
            body_text="Treść maila...",
        )
        proc = ProcessedMail(
            account="a",
            folder="INBOX",
            uidvalidity=1,
            uid=50,
            mail=parsed,
            final_importance=9,
            rule_reasons=(),
            analysis_reason="Ważne zebranie",
            action="read_now",
            language="pl",
        )

        server._loop = asyncio.get_running_loop()
        server._is_running = True
        server.broadcast_event(NewImportant(items=[proc], action=NotificationAction.BEEP))

        # Odbiór przez klienta WebSocket
        msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
        assert msg.type == WSMsgType.TEXT
        event_received = json.loads(msg.data)
        assert event_received["type"] == "NewImportant"
        assert event_received["data"]["mails"][0]["subject"] == "Pilne zebranie"

        await ws.close()

    finally:
        await client.close()


@pytest.mark.anyio
async def test_server_rate_limiting_and_body_limit(server_context):
    """Weryfikuje limit rozmiaru body (413) oraz ograniczenie zapytań."""
    app = create_app(server_context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # Żądanie z za dużym body (>64 KB)
        huge_payload = {"code": "A" * 70000, "device_name": "TooLarge"}
        resp = await client.post("/v1/pair", json=huge_payload)
        assert resp.status in (413, 400)

        # Sprawdzenie rate limitera na parowanie (więcej niż 5 prób/min z tego samego IP)
        # 5 prób z błędnym kodem
        for _ in range(5):
            await client.post("/v1/pair", json={"code": "WRONG1", "device_name": "Spammer"})

        # 6. próba powinna dostać 429
        resp = await client.post("/v1/pair", json={"code": "WRONG1", "device_name": "Spammer"})
        assert resp.status == 429

    finally:
        await client.close()


@pytest.mark.anyio
async def test_server_digest_endpoint(server_context):
    """Weryfikuje endpoint /v1/digest."""
    session = server_context.device_manager.start_pairing_session()
    _, token = server_context.device_manager.pair_device(session.code, "DigestTester")
    headers = {"Authorization": f"Bearer {token}"}

    app = create_app(server_context)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        resp = await client.get("/v1/digest?days=7", headers=headers)
        assert resp.status == 200
        data = await resp.json()
        assert "period" in data
        assert "topics" in data
        assert isinstance(data["topics"], list)
    finally:
        await client.close()


@pytest.mark.anyio
async def test_websocket_rejects_token_in_query_string(server_context, tmp_path: Path):
    """Token w adresie URL trafiłby do logów/historii — serwer przyjmuje go tylko w nagłówku."""
    from aiohttp import WSServerHandshakeError

    session = server_context.device_manager.start_pairing_session()
    _, token = server_context.device_manager.pair_device(session.code, "WsQuery")
    server = MobileServer(
        config=server_context.config,
        store=server_context.store,
        device_manager=server_context.device_manager,
        data_dir=tmp_path,
    )
    client = TestClient(TestServer(create_app(server.context)))
    await client.start_server()
    try:
        with pytest.raises(WSServerHandshakeError) as exc:
            await client.ws_connect(f"/v1/events?token={token}")
        assert exc.value.status == 401
        ok = await client.ws_connect("/v1/events", headers={"Authorization": f"Bearer {token}"})
        assert not ok.closed
        await ok.close()
    finally:
        await client.close()
