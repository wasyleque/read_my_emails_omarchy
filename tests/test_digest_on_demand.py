"""Podsumowanie: komputer nie czyta samoczynnie; serwer odpowiada szybko i sprawami otwartymi."""

from datetime import datetime, timezone

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PySide6.QtWidgets import QApplication

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.core.digest import Digest, Topic
from mailvoice.core.service import DigestReady
from mailvoice.core.store import Store
from mailvoice.server.api import ServerContext, create_app
from mailvoice.ui.main_window import MainWindow
from mailvoice.voice.tts import FakeSpeaker


def _topic(title: str, status: str) -> Topic:
    return Topic(
        title=title,
        participants=[],
        who_to_whom=["a -> b"],
        why="powód",
        status=status,
        last_activity=datetime.now(timezone.utc),
        importance=5,
        mail_count=2,
    )


def _digest() -> Digest:
    topics = [_topic(f"Czeka na mnie {i}", "oczekuje_na_mnie") for i in range(3)]
    topics += [_topic("Czeka na innych", "oczekuje_na_innych")]
    topics += [_topic(f"Zamknięte {i}", "zamknięte") for i in range(5)]
    topics += [_topic(f"Info {i}", "informacyjne") for i in range(4)]
    return Digest(period="ostatnie 30 dni", topics=topics)


class _RecordingDialog:
    def __init__(self):
        self.events, self.read = [], []

    def handle_event(self, event):
        self.events.append(event)

    def read_digest(self, topics, lang):
        self.read.append([t.title for t in topics])


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_digest_event_only_displays_and_never_reads_aloud(qapp):
    window = MainWindow(speaker=FakeSpeaker(), voice_dialog=_RecordingDialog())
    window._handle_service_event(DigestReady(digest=_digest()))
    assert window.voice_dialog.events == []  # żadnego samoczynnego czytania
    assert window.btn_read_digest.isEnabled()  # ale czytanie jest do wywołania przyciskiem


def test_read_button_reads_only_open_matters(qapp):
    window = MainWindow(speaker=FakeSpeaker(), voice_dialog=_RecordingDialog())
    window._display_digest(_digest())
    window._read_digest_aloud()
    assert window.voice_dialog.read == [
        ["Czeka na mnie 0", "Czeka na mnie 1", "Czeka na mnie 2", "Czeka na innych"]
    ]


def test_read_button_disabled_when_nothing_is_open(qapp):
    window = MainWindow(speaker=FakeSpeaker(), voice_dialog=_RecordingDialog())
    window._display_digest(Digest(period="p", topics=[_topic("Stare", "zamknięte")]))
    assert not window.btn_read_digest.isEnabled()


def test_digest_cards_are_capped_per_group(qapp):
    window = MainWindow(speaker=FakeSpeaker(), voice_dialog=_RecordingDialog())
    many = Digest(period="p", topics=[_topic(f"T{i}", "oczekuje_na_mnie") for i in range(120)])
    window._display_digest(many)
    cards = window.digest_container.findChildren(type(window.digest_container), "card")
    assert len(cards) <= MainWindow._MAX_CARDS_PER_GROUP


# ---------- serwer ----------
class _Service:
    def __init__(self):
        self.calls = []

    def request_digest(self, days=None, **kwargs):
        self.calls.append((days, kwargs))
        return _digest()


@pytest.mark.anyio
async def test_server_digest_returns_open_matters_with_counts_and_does_not_emit(tmp_path):
    service = _Service()
    ctx = ServerContext(
        config=AppConfig(),
        store=Store(tmp_path / "s.db"),
        device_manager=DeviceManager(tmp_path / "d.db"),
        service=service,
    )
    _, token = ctx.device_manager.pair_device(ctx.device_manager.start_pairing_session().code, "T")
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(TestServer(create_app(ctx)))
    await client.start_server()
    try:
        data = await (await client.get("/v1/digest?days=30", headers=headers)).json()
        assert [t["status"] for t in data["topics"]].count("zamknięte") == 0  # bez zamkniętych
        assert data["shown"] == 4 and data["total"] == 13
        assert data["counts"] == {
            "oczekuje_na_mnie": 3,
            "oczekuje_na_innych": 1,
            "zamknięte": 5,
            "informacyjne": 4,
        }
        assert service.calls[0][1]["emit"] is False  # zapytanie z telefonu nie wywołuje czytania
        assert service.calls[0][1]["llm_deadline_s"] <= 10  # szybka odpowiedź

        everything = await (await client.get("/v1/digest?days=30&all=1", headers=headers)).json()
        assert everything["shown"] == 13
        limited = await (
            await client.get("/v1/digest?days=30&all=1&limit=2", headers=headers)
        ).json()
        # limit liczy się w każdej grupie osobno: 2 (mnie) + 1 (innych) + 2 (zamknięte) + 2 (info)
        assert limited["shown"] == 7
        by_status = [t["status"] for t in limited["topics"]]
        assert by_status.count("oczekuje_na_innych") == 1  # mała grupa nie jest wypychana
        assert len(service.calls) == 1  # kolejne zapytania z pamięci podręcznej (bez liczenia)
    finally:
        await client.close()


def test_phone_digest_path_uses_a_short_per_call_timeout(tmp_path, monkeypatch):
    """Regresja: budżet ograniczał liczbę wywołań modelu, ale jedno zawieszone czekało 60 s."""
    from mailvoice.core import service as service_mod
    from mailvoice.core.analyzer import OllamaClient
    from mailvoice.core.config import OllamaConfig
    from mailvoice.core.service import MailService

    seen = {}

    def fake_build(store, client, config, **kwargs):
        seen["timeout"] = client.cfg.timeout_s
        seen["budget"] = kwargs["llm_budget"]
        return Digest(period="p", topics=[])

    monkeypatch.setattr(service_mod, "build_digest", fake_build)
    cfg = AppConfig()
    svc = MailService.__new__(MailService)  # bez sieci i bez sejfu: testujemy tylko request_digest
    svc.config = cfg
    svc.store = Store(tmp_path / "s.db")
    svc.ollama_client = OllamaClient(OllamaConfig(timeout_s=120.0))
    svc._clock = lambda: datetime.now(timezone.utc)
    svc._emit = lambda event: None

    svc.request_digest(days=30, emit=False, llm_budget=3, llm_timeout_s=6.0)
    assert seen == {"timeout": 6.0, "budget": 3}
    svc.request_digest(days=30)  # zwykłe wywołanie (okno na komputerze) zachowuje długi limit
    assert seen["timeout"] == 120.0


@pytest.mark.anyio
async def test_server_digest_limit_does_not_push_out_the_waiting_for_others_group(tmp_path):
    """Regresja z telefonu: 134 spraw „czeka na mnie” zajmowało cały limit i grupa „czeka na
    innych” miała licznik 36, ale pustą listę."""

    class _Big:
        def request_digest(self, days=None, **kwargs):
            topics = [_topic(f"M{i}", "oczekuje_na_mnie") for i in range(30)]
            topics += [_topic(f"I{i}", "oczekuje_na_innych") for i in range(6)]
            return Digest(period="p", topics=topics)

    ctx = ServerContext(
        config=AppConfig(),
        store=Store(tmp_path / "s.db"),
        device_manager=DeviceManager(tmp_path / "d.db"),
        service=_Big(),
    )
    _, token = ctx.device_manager.pair_device(ctx.device_manager.start_pairing_session().code, "T")
    client = TestClient(TestServer(create_app(ctx)))
    await client.start_server()
    try:
        data = await (
            await client.get(
                "/v1/digest?days=30&limit=10", headers={"Authorization": f"Bearer {token}"}
            )
        ).json()
        statuses = [t["status"] for t in data["topics"]]
        assert statuses.count("oczekuje_na_mnie") == 10  # limit na grupę
        assert statuses.count("oczekuje_na_innych") == 6  # licznik 6 = 6 pozycji na liście
        assert data["counts"]["oczekuje_na_innych"] == 6
    finally:
        await client.close()
