"""Przycisk „VIP…” (lustro „Ignoruj”): reguły VIP z tematem, pipeline, serwer, Ustawienia."""

import json
from datetime import datetime, timezone

import httpx
import pytest
from aiohttp.test_utils import TestClient, TestServer
from PySide6.QtWidgets import QApplication, QMessageBox

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.devices import DeviceManager
from mailvoice.core.digest import build_digest
from mailvoice.core.ignore import IgnoreRule, MailRule, add_vip_rule, rule_for_mail
from mailvoice.core.pipeline import PipelineDeps, run_cycle
from mailvoice.core.rules import MailInfo, Rules, evaluate
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.server.api import ServerContext, create_app
from mailvoice.ui.ignore_dialog import IgnoreDialog
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker
from tests.test_imap_fetch import FakeMailboxClient
from tests.test_pipeline import _make_email_bytes


def test_vip_similar_rule_matches_only_similar_subjects():
    rule = rule_for_mail("similar", "Dostawca <faktury@dostawca.pl>", "Faktura nr 12 za wrzesień")
    rules = Rules(vip_rules=(rule,))
    ok = evaluate(
        MailInfo("Dostawca <faktury@dostawca.pl>", "Faktura nr 99 za październik", ""), rules
    )
    other = evaluate(MailInfo("Dostawca <faktury@dostawca.pl>", "Newsletter", ""), rules)
    assert ok.force_important and ok.reasons == ("vip_sender",)
    assert not other.force_important


def test_vip_sender_and_domain_modes():
    by_domain = rule_for_mail("domain", "A <a@firma.pl>", "x")
    res = evaluate(MailInfo("B <b@firma.pl>", "cokolwiek", ""), Rules(vip_rules=(by_domain,)))
    assert res.force_important


def test_ignore_still_beats_vip_rule():
    rule = MailRule(sender="a@x.pl")
    res = evaluate(MailInfo("a@x.pl", "s", ""), Rules(vip_rules=(rule,), ignore_rules=(rule,)))
    assert res.blocked


def test_add_vip_rule_removes_identical_ignore_rule_and_roundtrips():
    rule = MailRule(sender="a@x.pl", subject="faktura")
    cfg = AppConfig(ignore_rules=[rule, IgnoreRule(sender="inny@x.pl")])
    out = add_vip_rule(cfg, rule)
    assert out.vip_rules == [rule] and out.ignore_rules == [IgnoreRule(sender="inny@x.pl")]
    again = AppConfig.from_dict(json.loads(json.dumps(out.to_dict())))
    assert again.vip_rules == [rule]


def _run(tmp_path, vip_rules, subject):
    store = Store(tmp_path / "s.db")
    store.set_last_uid("acc", "INBOX", 1, 0)
    client = FakeMailboxClient(uidvalidity=1)
    client.folders["INBOX"][1] = _make_email_bytes(
        sender="Dostawca <faktury@dostawca.pl>", subject=subject, body="treść", message_id="<m@x>"
    )
    cfg = AppConfig(
        accounts=[AccountConfig(name="acc", host="h", sent_folder="")],
        importance_threshold=6,
        vip_rules=vip_rules,
    )

    def handler(request):
        resp = {"importance": 0, "reason": "nic", "action": "ignore", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    ollama = OllamaClient(cfg.ollama, transport=httpx.MockTransport(handler))
    deps = PipelineDeps(
        config=cfg, store=store, client_factory=lambda a: client, ollama_client=ollama
    )
    return run_cycle(deps)


def test_pipeline_promotes_similar_vip_mail_even_when_model_says_zero(tmp_path):
    rule = rule_for_mail("similar", "faktury@dostawca.pl", "Faktura nr 1 za wrzesień")
    assert len(_run(tmp_path, [rule], "Faktura nr 55 za październik").important) == 1


def test_pipeline_does_not_promote_other_mail_from_the_same_vip_sender(tmp_path):
    rule = rule_for_mail("similar", "faktury@dostawca.pl", "Faktura nr 1 za wrzesień")
    assert _run(tmp_path, [rule], "Newsletter promocyjny").important == []


class _NoModel:
    def chat_json(self, *a, **k):
        raise RuntimeError("bez modelu")


def test_digest_marks_thread_matching_vip_rule_as_vip():
    store = Store()
    store.save_mail_index(
        MailIndexRecord(
            account="a",
            folder="INBOX",
            uidvalidity=1,
            uid=1,
            message_id="<1@x>",
            thread_key="t",
            date=datetime.now(timezone.utc).isoformat(),
            sender="Dostawca <faktury@dostawca.pl>",
            recipients="ja@x.pl",
            subject="Faktura nr 7",
            importance=1,
            why="w",
            summary="s",
            direction="in",
            risk="low",
            risk_reasons="",
        )
    )
    rule = MailRule(sender="faktury@dostawca.pl", subject="faktura")
    digest = build_digest(store, _NoModel(), AppConfig(vip_rules=[rule], importance_threshold=6))
    assert digest.topics[0].vip and digest.topics[0].importance >= 6


# ---------- okno wyboru ----------
@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_dialog_vip_kind_uses_vip_texts(qapp):
    from mailvoice.ui.i18n import tr

    dlg = IgnoreDialog("A <a@x.pl>", "Faktura nr 3", kind="vip")
    assert dlg.windowTitle() == tr("vip_title") and dlg.mode() == "similar"
    assert tr("vip_mode_domain") in [b.text() for b in dlg._buttons.values()]


# ---------- serwer ----------
@pytest.fixture
def ctx(tmp_path):
    return ServerContext(
        config=AppConfig(importance_threshold=6),
        store=Store(tmp_path / "s.db"),
        device_manager=DeviceManager(tmp_path / "d.db"),
    )


@pytest.mark.anyio
async def test_vip_endpoint_creates_rule_and_rejects_bad_requests(ctx):
    ctx.store.save_mail_index(
        MailIndexRecord(
            account="a",
            folder="INBOX",
            uidvalidity=1,
            uid=1,
            message_id="<1@x>",
            thread_key="t",
            date=datetime.now(timezone.utc).isoformat(),
            sender="Anna <anna@firma.pl>",
            recipients="ja@x.pl",
            subject="Umowa",
            importance=9,
            why="w",
            summary="s",
            direction="in",
        )
    )
    got: list[MailRule] = []
    ctx.on_vip = got.append
    _, token = ctx.device_manager.pair_device(ctx.device_manager.start_pairing_session().code, "T")
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(TestServer(create_app(ctx)))
    await client.start_server()
    try:
        mail = (await (await client.get("/v1/mails/important", headers=headers)).json())["mails"][0]
        url = f"/v1/mails/{mail['id']}/vip"
        ok = await client.post(url, json={"mode": "sender"}, headers=headers)
        assert ok.status == 200 and got == [MailRule(sender="anna@firma.pl")]
        assert (await client.post(url, json={"mode": "xx"}, headers=headers)).status == 400
        assert (await client.post("/v1/mails/brak/vip", json={}, headers=headers)).status == 404
        assert (await client.post(url, json={"mode": "sender"})).status == 401
        ctx.on_vip = None
        assert (await client.post(url, json={"mode": "sender"}, headers=headers)).status == 503
    finally:
        await client.close()


# ---------- Ustawienia ----------
class _Secrets:
    def get(self, a):
        return None

    def set(self, a, s):
        pass

    def delete(self, a):
        pass


def test_settings_vip_list_splits_plain_senders_and_subject_rules(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    cfg = AppConfig(vip_senders=["@vip.pl"], vip_rules=[MailRule("a@x.pl", "faktura")])
    saved = []
    dlg = SettingsDialog(
        config=cfg,
        config_path=tmp_path / "c.json",
        secret_store=_Secrets(),
        speaker=FakeSpeaker(),
        on_config_saved=saved.append,
    )
    assert dlg.list_vip.count() == 2
    dlg.txt_vip.setText("@nowy.pl")
    dlg._add_vip()
    dlg.txt_vip.setText("b@x.pl")
    dlg.txt_vip_subject.setText("umowa")
    dlg._add_vip()
    dlg._on_save()
    out = saved[0]
    assert out.vip_senders == ["@vip.pl", "@nowy.pl"]  # stary format dla samego nadawcy
    assert out.vip_rules == [MailRule("a@x.pl", "faktura"), MailRule("b@x.pl", "umowa")]
