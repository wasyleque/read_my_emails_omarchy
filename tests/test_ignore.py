"""Ignorowanie maili: nadawca, domena, „podobne” maile; konfiguracja; pełna ścieżka pipeline."""

import json

import httpx
import pytest

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.ignore import (
    IgnoreRule,
    add_ignore_rule,
    is_ignored,
    normalize_subject,
    rule_for_mail,
    subject_signature,
)
from mailvoice.core.pipeline import PipelineDeps, run_cycle
from mailvoice.core.rules import MailInfo, Rules, evaluate
from mailvoice.core.store import Store
from tests.test_imap_fetch import FakeMailboxClient
from tests.test_pipeline import _make_email_bytes


def test_signature_strips_prefixes_digits_and_keeps_first_words():
    assert subject_signature("Re: Fwd: [EXT] Faktura nr 12/2026 za wrzesień") == "faktura nr za"
    assert subject_signature("Newsletter tygodniowy #41") == "newsletter tygodniowy"
    assert normalize_subject("ODP: Spotkanie 12.10") == "spotkanie"
    assert subject_signature("1234 !!!") == ""


def test_similar_mode_ignores_same_pattern_but_not_other_mail_from_same_sender():
    sender = "Sklep <info@sklep.pl>"
    rule = rule_for_mail("similar", sender, "Twoje zamówienie nr 55 zostało wysłane")
    assert rule.sender == "info@sklep.pl" and rule.subject == "twoje zamówienie nr"
    assert rule.matches(sender, "Twoje zamówienie nr 99 zostało wysłane")
    assert rule.matches(sender, "RE: Twoje zamówienie nr 7")
    assert not rule.matches(sender, "Faktura do zamówienia")  # inny mail od tego samego nadawcy
    assert not rule.matches("Ktoś <inny@x.pl>", "Twoje zamówienie nr 1")  # inny nadawca


def test_sender_and_domain_modes():
    by_sender = rule_for_mail("sender", "A <a@firma.pl>", "dowolny temat")
    assert by_sender.matches("A <a@firma.pl>", "cokolwiek")
    assert not by_sender.matches("B <b@firma.pl>", "cokolwiek")
    by_domain = rule_for_mail("domain", "A <a@firma.pl>", "x")
    assert by_domain.sender == "@firma.pl"
    assert by_domain.matches("B <b@firma.pl>", "x") and not by_domain.matches("c@inna.pl", "x")


def test_similar_falls_back_to_sender_when_subject_has_no_words():
    assert rule_for_mail("similar", "a@x.pl", "12345").subject == ""


def test_subject_only_rule_is_a_global_pattern():
    rule = IgnoreRule(subject="newsletter")
    assert rule.matches("kto@bądź.pl", "Weekly NEWSLETTER 42")
    assert not rule.matches("kto@bądź.pl", "Umowa")


def test_empty_rule_matches_nothing():
    assert not IgnoreRule().is_valid() and not IgnoreRule().matches("a@b.pl", "x")


def test_rules_evaluate_marks_ignored_as_blocked():
    rules = Rules(ignore_rules=(rule_for_mail("sender", "a@x.pl", "t"),))
    res = evaluate(MailInfo(sender="a@x.pl", subject="s", body="b"), rules)
    assert res.blocked and res.reasons == ("ignored_rule",)


def test_ignore_wins_over_vip():
    rules = Rules(vip_senders=("@x.pl",), ignore_rules=(IgnoreRule(sender="a@x.pl"),))
    assert evaluate(MailInfo(sender="a@x.pl", subject="s", body="b"), rules).blocked


def test_add_rule_dedupes_and_survives_config_roundtrip():
    cfg = AppConfig()
    rule = IgnoreRule(sender="a@x.pl", subject="newsletter")
    cfg = add_ignore_rule(add_ignore_rule(cfg, rule), rule)
    assert cfg.ignore_rules == [rule]
    again = AppConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert again.ignore_rules == [rule]


def test_config_ignores_garbage_rules():
    cfg = AppConfig.from_dict(
        {"ignore_rules": ["x", {"sender": "", "subject": ""}, {"sender": "ok@x.pl"}, 5]}
    )
    assert cfg.ignore_rules == [IgnoreRule(sender="ok@x.pl")]


def _run(tmp_path, ignore_rules, subject="Newsletter tygodniowy 41"):
    store = Store(tmp_path / "s.db")
    store.set_last_uid("acc", "INBOX", 1, 0)
    client = FakeMailboxClient(uidvalidity=1)
    client.folders["INBOX"][1] = _make_email_bytes(
        sender="Firma <info@firma.pl>", subject=subject, body="treść", message_id="<m1@x>"
    )
    cfg = AppConfig(
        accounts=[AccountConfig(name="acc", host="h", sent_folder="")],
        importance_threshold=6,
        ignore_rules=ignore_rules,
    )
    calls = []

    def handler(request):
        calls.append(1)
        resp = {"importance": 9, "reason": "r", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    ollama = OllamaClient(cfg.ollama, transport=httpx.MockTransport(handler))
    deps = PipelineDeps(
        config=cfg, store=store, client_factory=lambda a: client, ollama_client=ollama
    )
    return run_cycle(deps), calls


def test_pipeline_skips_ignored_mail_without_asking_the_model(tmp_path):
    rule = rule_for_mail("similar", "info@firma.pl", "Newsletter tygodniowy 40")
    result, calls = _run(tmp_path, [rule])
    assert result.important == [] and calls == []  # nawet nie odpytujemy modelu


def test_pipeline_keeps_other_mail_from_same_sender(tmp_path):
    rule = rule_for_mail("similar", "info@firma.pl", "Newsletter tygodniowy 40")
    result, calls = _run(tmp_path, [rule], subject="Umowa do podpisu")
    assert len(result.important) == 1 and calls


@pytest.mark.parametrize("mode", ["similar", "sender", "domain"])
def test_is_ignored_helper(mode):
    rule = rule_for_mail(mode, "Firma <info@firma.pl>", "Newsletter tygodniowy 40")
    assert is_ignored([rule], "Firma <info@firma.pl>", "Newsletter tygodniowy 41")
