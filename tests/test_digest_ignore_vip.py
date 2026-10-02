"""Podsumowanie tematów stosuje te same reguły co lista maili: ignorowanie i priorytet VIP."""

import dataclasses
from datetime import datetime, timezone

from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.digest import build_digest
from mailvoice.core.ignore import IgnoreRule, rule_for_mail
from mailvoice.core.store import MailIndexRecord, Store


class _NoModel:
    """Model niedostępny: podsumowanie ma działać na opisach awaryjnych."""

    def chat_json(self, *a, **k):
        raise RuntimeError("bez modelu")


def _config(**overrides) -> AppConfig:
    base = AppConfig(
        accounts=[AccountConfig(name="praca", host="h", username="ja@corp.com")],
        importance_threshold=6,
        digest_days=30,
    )
    return dataclasses.replace(base, **overrides)


def _save(
    store,
    uid,
    sender,
    subject,
    thread,
    direction="in",
    importance=2,
    recipients="ja@corp.com",
    risk="low",
    risk_reasons="",
):
    store.save_mail_index(
        MailIndexRecord(
            account="praca",
            folder="INBOX" if direction == "in" else "Sent",
            uidvalidity=1,
            uid=uid,
            message_id=f"<{uid}@x>",
            thread_key=thread,
            date=datetime.now(timezone.utc).isoformat(),
            sender=sender,
            recipients=recipients,
            subject=subject,
            importance=importance,
            why="w",
            summary="s",
            direction=direction,
            risk=risk,
            risk_reasons=risk_reasons,
        )
    )


def _titles(digest):
    return [t.title for t in digest.topics]


def test_ignored_sender_thread_disappears_others_stay():
    store = Store()
    _save(store, 1, "Sklep <info@sklep.pl>", "Newsletter tygodniowy 40", "t1")
    _save(store, 2, "Szef <szef@firma.pl>", "Umowa do podpisu", "t2")
    cfg = _config(ignore_rules=[rule_for_mail("sender", "info@sklep.pl", "x")])
    digest = build_digest(store, _NoModel(), cfg)
    assert [t.title for t in digest.topics if "Newsletter" in t.title] == []
    assert any("Umowa" in t for t in _titles(digest))


def test_similar_mode_hides_only_the_similar_thread_from_same_sender():
    store = Store()
    _save(store, 1, "Sklep <info@sklep.pl>", "Newsletter tygodniowy 40", "t1")
    _save(store, 2, "Sklep <info@sklep.pl>", "Faktura do zamówienia", "t2")
    cfg = _config(
        ignore_rules=[rule_for_mail("similar", "info@sklep.pl", "Newsletter tygodniowy 41")]
    )
    titles = _titles(build_digest(store, _NoModel(), cfg))
    assert not any("Newsletter" in t for t in titles) and any("Faktura" in t for t in titles)


def test_domain_rule_and_legacy_blocked_senders_are_honoured():
    store = Store()
    _save(store, 1, "A <a@spam.pl>", "Oferta A", "t1")
    _save(store, 2, "B <b@stary-blok.pl>", "Oferta B", "t2")
    _save(store, 3, "C <c@dobra.pl>", "Sprawa C", "t3")
    cfg = _config(ignore_rules=[IgnoreRule(sender="@spam.pl")], blocked_senders=["stary-blok"])
    assert _titles(build_digest(store, _NoModel(), cfg)) == ["Sprawa C"]


def test_thread_where_i_replied_to_an_ignored_sender_also_disappears():
    store = Store()
    _save(store, 1, "A <a@spam.pl>", "Oferta", "t1")
    _save(store, 2, "ja@corp.com", "Re: Oferta", "t1", direction="out", recipients="a@spam.pl")
    cfg = _config(ignore_rules=[IgnoreRule(sender="a@spam.pl")])
    assert build_digest(store, _NoModel(), cfg).topics == []


def test_thread_started_by_me_to_someone_not_ignored_is_kept():
    store = Store()
    _save(
        store, 1, "ja@corp.com", "Pytanie o ofertę", "t1", direction="out", recipients="x@dobra.pl"
    )
    cfg = _config(ignore_rules=[IgnoreRule(sender="a@spam.pl")])
    assert len(build_digest(store, _NoModel(), cfg).topics) == 1


def test_vip_thread_is_marked_floored_and_listed_first_within_status():
    store = Store()
    _save(store, 1, "Ktoś <ktos@inna.pl>", "Zwykła sprawa", "t1", importance=5)
    _save(store, 2, "Szef <szef@firma.pl>", "Sprawa szefa", "t2", importance=1)
    cfg = _config(vip_senders=["@firma.pl"])
    digest = build_digest(store, _NoModel(), cfg)
    vip = next(t for t in digest.topics if "szefa" in t.title)
    assert vip.vip and vip.importance >= 6  # gwarancja progu, jak dla maila
    assert digest.topics[
        0
    ].vip  # mimo niższej ważności bazowej stoi przed zwykłą sprawą (ta sama grupa)


def test_known_correspondent_in_vip_mode_marks_thread_as_vip():
    store = Store()
    _save(store, 1, "ja@corp.com", "Pytanie", "t0", direction="out", recipients="anna@firma.pl")
    _save(store, 2, "Anna <anna@firma.pl>", "Odpowiedź Anny", "t2", importance=1)
    on = build_digest(store, _NoModel(), _config(auto_vip="vip"))
    off = build_digest(store, _NoModel(), _config(auto_vip="bonus"))
    assert next(t for t in on.topics if "Anny" in t.title).vip
    assert not next(t for t in off.topics if "Anny" in t.title).vip


def test_spoofed_vip_with_phishing_signals_does_not_get_priority():
    store = Store()
    _save(
        store,
        1,
        "Szef <szef@firma.pl>",
        "Pilne hasło",
        "t1",
        importance=1,
        risk="high",
        risk_reasons="SPF fail",
    )
    digest = build_digest(store, _NoModel(), _config(vip_senders=["@firma.pl"]))
    assert not digest.topics[0].vip and digest.topics[0].importance < 6
