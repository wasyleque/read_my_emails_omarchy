"""VIP gwarantuje powiadomienie; automatyczni VIP z folderu Wysłane (off/bonus/vip)."""

import json

import httpx
import pytest

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.pipeline import PipelineDeps, run_cycle
from mailvoice.core.rules import MailInfo, Rules, evaluate, is_automated_address
from mailvoice.core.store import MailIndexRecord, Store
from tests.test_imap_fetch import FakeMailboxClient
from tests.test_pipeline import _make_email_bytes

KNOWN = frozenset({"anna@firma.pl"})


def _mail(sender="Anna <anna@firma.pl>"):
    return MailInfo(sender=sender, subject="s", body="b")


# ---------- reguły ----------
def test_manual_vip_forces_importance():
    res = evaluate(_mail(), Rules(vip_senders=("@firma.pl",)))
    assert res.force_important and res.reasons == ("vip_sender",)


@pytest.mark.parametrize(
    "mode, bonus, force",
    [("off", 0, False), ("bonus", 3, False), ("vip", 3, True)],
)
def test_auto_vip_modes_for_known_address(mode, bonus, force):
    res = evaluate(_mail(), Rules(known_addresses=KNOWN, auto_vip=mode))
    assert (res.score_bonus, res.force_important) == (bonus, force)


def test_known_domain_never_forces_even_in_vip_mode():
    rules = Rules(known_domains=frozenset({"firma.pl"}), auto_vip="vip")
    res = evaluate(_mail("Ktoś <ktos@firma.pl>"), rules)
    assert res.score_bonus == 2 and not res.force_important


def test_automated_addresses_are_never_known_correspondents():
    assert is_automated_address("no-reply@sklep.pl") and is_automated_address("Newsletter@x.pl")
    rules = Rules(known_addresses=frozenset({"noreply@sklep.pl"}), auto_vip="vip")
    res = evaluate(_mail("Sklep <noreply@sklep.pl>"), rules)
    assert res.score_bonus == 0 and not res.force_important


# ---------- pełna ścieżka pipeline (model daje ocenę 0) ----------
def _run(tmp_path, *, sender, vip=(), auto_vip="bonus", sent_to=None, body="Dzień dobry"):
    store = Store(tmp_path / "s.db")
    store.set_last_uid("acc", "INBOX", 1, 0)  # folder znany: mail jest nowy
    if sent_to:
        store.save_mail_index(
            MailIndexRecord(
                account="acc",
                folder="Sent",
                uidvalidity=9,
                uid=1,
                message_id="<o@x>",
                thread_key="t",
                date="2999-01-01T00:00:00+00:00",
                sender="ja@x.pl",
                recipients=sent_to,
                subject="s",
                importance=0,
                why="",
                summary="",
                direction="out",
            )
        )
    client = FakeMailboxClient(uidvalidity=1)
    client.folders["INBOX"][1] = _make_email_bytes(
        sender=sender, subject="Coś", body=body, message_id="<m1@x>"
    )
    cfg = AppConfig(
        accounts=[AccountConfig(name="acc", host="h", username="ja@x.pl", sent_folder="")],
        importance_threshold=6,
        vip_senders=list(vip),
        auto_vip=auto_vip,
    )

    def handler(request):
        resp = {"importance": 0, "reason": "nic", "action": "ignore", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    ollama = OllamaClient(cfg.ollama, transport=httpx.MockTransport(handler))
    deps = PipelineDeps(
        config=cfg, store=store, client_factory=lambda a: client, ollama_client=ollama
    )
    return run_cycle(deps)


def test_manual_vip_is_important_even_when_model_says_zero(tmp_path):
    res = _run(tmp_path, sender="Szef <szef@firma.pl>", vip=["@firma.pl"])
    assert len(res.important) == 1
    assert res.important[0].final_importance >= 6


def test_non_vip_with_zero_score_stays_unimportant(tmp_path):
    assert _run(tmp_path, sender="Obcy <obcy@inna.pl>").important == []


def test_auto_vip_mode_vip_promotes_known_recipient(tmp_path):
    res = _run(tmp_path, sender="Anna <anna@firma.pl>", auto_vip="vip", sent_to="anna@firma.pl")
    assert len(res.important) == 1


def test_auto_vip_bonus_mode_alone_does_not_force(tmp_path):
    res = _run(tmp_path, sender="Anna <anna@firma.pl>", auto_vip="bonus", sent_to="anna@firma.pl")
    assert res.important == []  # 0 + 3 < próg 6


def test_auto_vip_off_ignores_sent_folder(tmp_path):
    res = _run(tmp_path, sender="Anna <anna@firma.pl>", auto_vip="off", sent_to="anna@firma.pl")
    assert res.important == []


def test_spoofed_vip_with_phishing_signals_is_not_forced(tmp_path):
    body = "Pilne! Zaloguj się i podaj hasło: https://fałszywy.example/login natychmiast"
    res = _run(tmp_path, sender="Szef <szef@firma.pl>", vip=["@firma.pl"], body=body)
    # żaden mail z sygnałem phishingu nie może zostać wymuszony do „ważnych” przez VIP
    assert all(m.final_importance < 6 for m in res.important)
