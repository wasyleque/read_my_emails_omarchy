"""Przycisk „Ignoruj”: okno wyboru, lista na komputerze, endpoint serwera i filtr listy ważnych."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PySide6.QtWidgets import QApplication

from mailvoice.core.config import AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.core.ignore import IgnoreRule, add_ignore_rule, rule_for_mail
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import ProcessedMail
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.server.api import ServerContext, create_app
from mailvoice.ui.ignore_dialog import IgnoreDialog
from mailvoice.ui.main_window import MainWindow
from mailvoice.voice.tts import FakeSpeaker


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _item(uid: int, sender: str, subject: str) -> ProcessedMail:
    mail = ParsedMail(
        message_id=f"<{uid}@x>",
        sender=sender,
        subject=subject,
        date=None,
        in_reply_to=None,
        references=(),
        body_text="",
    )
    return ProcessedMail(
        account="a",
        folder="INBOX",
        uidvalidity=1,
        uid=uid,
        mail=mail,
        final_importance=8,
        rule_reasons=(),
        analysis_reason="ważne",
        action="read_now",
        language="pl",
    )


# ---------- okno wyboru ----------
def test_dialog_defaults_to_similar_and_previews_the_rule(qapp):
    dlg = IgnoreDialog("Sklep <info@sklep.pl>", "Twoje zamówienie nr 5 wysłane")
    assert dlg.mode() == "similar"
    assert "info@sklep.pl" in dlg._preview.text() and "zamówienie" in dlg._preview.text()
    dlg._buttons["domain"].setChecked(True)
    assert dlg.mode() == "domain" and "@sklep.pl" in dlg._preview.text()


# ---------- lista na komputerze ----------
def test_rows_matching_the_rule_are_removed_others_stay(qapp):
    window = MainWindow(speaker=FakeSpeaker())
    window._add_important_mail(_item(1, "Sklep <info@sklep.pl>", "Newsletter tygodniowy 40"))
    window._add_important_mail(_item(2, "Sklep <info@sklep.pl>", "Faktura do zamówienia"))
    window._add_important_mail(_item(3, "Szef <szef@firma.pl>", "Umowa"))
    rule = rule_for_mail("similar", "info@sklep.pl", "Newsletter tygodniowy 41")
    assert window._remove_ignored_rows(rule) == 1
    assert [i.uid for i in window.important_items] == [2, 3]
    assert window.tbl_mails.rowCount() == 2  # wiersze i elementy pozostają zsynchronizowane
    assert window.tbl_mails.item(0, 1).text() == "Faktura do zamówienia"


# ---------- serwer ----------
@pytest.fixture
def ctx(tmp_path: Path):
    return ServerContext(
        config=AppConfig(importance_threshold=6),
        store=Store(tmp_path / "s.db"),
        device_manager=DeviceManager(tmp_path / "d.db"),
    )


def _save(store: Store, uid: int, sender: str, subject: str) -> None:
    store.save_mail_index(
        MailIndexRecord(
            account="a",
            folder="INBOX",
            uidvalidity=1,
            uid=uid,
            message_id=f"<{uid}@x>",
            thread_key=f"t{uid}",
            date=datetime.now(timezone.utc).isoformat(),
            sender=sender,
            recipients="ja@x.pl",
            subject=subject,
            importance=9,
            why="ważne",
            summary="s",
            direction="in",
        )
    )


@pytest.mark.anyio
async def test_ignore_endpoint_creates_rule_and_list_hides_matching_mail(ctx):
    _save(ctx.store, 1, "Sklep <info@sklep.pl>", "Newsletter tygodniowy 40")
    _save(ctx.store, 2, "Szef <szef@firma.pl>", "Umowa")
    received: list[IgnoreRule] = []

    def on_ignore(rule):
        received.append(rule)
        ctx.config = add_ignore_rule(ctx.config, rule)  # tak robi MainWindow + update_config

    ctx.on_ignore = on_ignore
    _, token = ctx.device_manager.pair_device(ctx.device_manager.start_pairing_session().code, "T")
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(TestServer(create_app(ctx)))
    await client.start_server()
    try:
        mails = (await (await client.get("/v1/mails/important", headers=headers)).json())["mails"]
        assert len(mails) == 2
        target = next(m for m in mails if "Newsletter" in m["subject"])

        bad = await client.post(
            f"/v1/mails/{target['id']}/ignore", json={"mode": "wszystko"}, headers=headers
        )
        assert bad.status == 400 and received == []

        ok = await client.post(
            f"/v1/mails/{target['id']}/ignore", json={"mode": "similar"}, headers=headers
        )
        assert ok.status == 200
        assert (
            received[0].sender == "info@sklep.pl" and received[0].subject == "newsletter tygodniowy"
        )

        after = (await (await client.get("/v1/mails/important", headers=headers)).json())["mails"]
        assert [m["subject"] for m in after] == ["Umowa"]  # zignorowany zniknął z listy telefonu

        missing = await client.post("/v1/mails/nieistnieje/ignore", json={}, headers=headers)
        assert missing.status == 404
        unauth = await client.post(f"/v1/mails/{target['id']}/ignore", json={"mode": "sender"})
        assert unauth.status == 401
    finally:
        await client.close()


@pytest.mark.anyio
async def test_ignore_unavailable_without_callback(ctx):
    _save(ctx.store, 1, "a@x.pl", "Temat")
    _, token = ctx.device_manager.pair_device(ctx.device_manager.start_pairing_session().code, "T")
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(TestServer(create_app(ctx)))
    await client.start_server()
    try:
        mail = (await (await client.get("/v1/mails/important", headers=headers)).json())["mails"][0]
        resp = await client.post(
            f"/v1/mails/{mail['id']}/ignore", json={"mode": "sender"}, headers=headers
        )
        assert resp.status == 503
    finally:
        await client.close()


@pytest.mark.anyio
async def test_vip_endpoint_refuses_suspicious_mail_but_ignore_still_works(ctx):
    """Podrobiony nadawca nie zostaje VIP-em, nawet gdy ktoś pominie przycisk w aplikacji."""
    _save(ctx.store, 1, "Bank <alert@fake-bank.xyz>", "Konto zawieszone")
    record = ctx.store.get_mail_index("a", "INBOX", 1, 1)
    ctx.store.save_mail_index(
        MailIndexRecord(**{**record.__dict__, "risk": "high", "risk_reasons": "Podejrzany link"})
    )
    _save(ctx.store, 2, "Szef <szef@firma.pl>", "Umowa")
    got: dict[str, list] = {"vip": [], "ignore": []}
    ctx.on_vip = got["vip"].append
    ctx.on_ignore = got["ignore"].append
    _, token = ctx.device_manager.pair_device(ctx.device_manager.start_pairing_session().code, "T")
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(TestServer(create_app(ctx)))
    await client.start_server()
    try:
        mails = (await (await client.get("/v1/mails/important", headers=headers)).json())["mails"]
        bad = next(m for m in mails if "Konto" in m["subject"])
        good = next(m for m in mails if m["subject"] == "Umowa")

        refused = await client.post(
            f"/v1/mails/{bad['id']}/vip", json={"mode": "sender"}, headers=headers
        )
        assert refused.status == 403 and got["vip"] == []

        ignored = await client.post(
            f"/v1/mails/{bad['id']}/ignore", json={"mode": "sender"}, headers=headers
        )
        assert ignored.status == 200 and len(got["ignore"]) == 1  # ignorowanie zawsze wolno

        accepted = await client.post(
            f"/v1/mails/{good['id']}/vip", json={"mode": "sender"}, headers=headers
        )
        assert accepted.status == 200 and len(got["vip"]) == 1
    finally:
        await client.close()


def test_vip_button_is_disabled_for_suspicious_mail_on_desktop(qapp):
    window = MainWindow(speaker=FakeSpeaker())
    safe = _item(1, "Szef <szef@firma.pl>", "Umowa")
    phish = _item(2, "Bank <alert@fake-bank.xyz>", "Konto")
    object.__setattr__(phish, "suspicious", True)
    object.__setattr__(phish, "risk_level", "high")
    window._add_important_mail(safe)
    window._add_important_mail(phish)
    assert window.tbl_mails.cellWidget(0, 6).isEnabled()
    assert not window.tbl_mails.cellWidget(1, 6).isEnabled()
