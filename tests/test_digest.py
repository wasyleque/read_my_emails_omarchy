"""Testy modułu podsumowań wątków (core/digest.py)."""

import json
from datetime import datetime, timedelta, timezone

import httpx

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig
from mailvoice.core.digest import Digest, build_digest
from mailvoice.core.store import MailIndexRecord, Store


def _make_config() -> AppConfig:
    return AppConfig(
        accounts=[
            AccountConfig(
                name="praca",
                host="imap.corp.com",
                port=993,
                username="me@corp.com",
                use_ssl=True,
            )
        ],
        my_addresses=["me.alias@corp.com"],
        digest_days=30,
        ollama=OllamaConfig(),
    )


def _make_record(
    thread_key: str,
    subject: str,
    sender: str,
    recipients: str,
    uid: int = 1,
    date: str | None = None,
    importance: int = 5,
    why: str = "Ważna sprawa",
    summary: str = "Krótkie streszczenie",
    direction: str = "in",
) -> MailIndexRecord:
    dt = date or datetime.now(timezone.utc).isoformat()
    return MailIndexRecord(
        account="praca",
        folder="INBOX" if direction == "in" else "Sent",
        uidvalidity=1,
        uid=uid,
        message_id=f"<msg-{uid}@corp.com>",
        thread_key=thread_key,
        date=dt,
        sender=sender,
        recipients=recipients,
        subject=subject,
        importance=importance,
        why=why,
        summary=summary,
        direction=direction,
    )


def _llm_client(handler) -> OllamaClient:
    cfg = OllamaConfig(prefer="lan")
    return OllamaClient(cfg, transport=httpx.MockTransport(handler))


def test_build_digest_empty():
    store = Store(":memory:")
    config = _make_config()

    def handler(request):
        raise AssertionError("LLM should not be called for empty digest")

    client = _llm_client(handler)
    digest = build_digest(store, client, config)

    assert isinstance(digest, Digest)
    assert len(digest.topics) == 0
    assert "30 dni" in digest.period


def test_build_digest_multi_threads_and_status():
    store = Store(":memory:")
    config = _make_config()

    now = datetime.now(timezone.utc)
    t1_date = (now - timedelta(hours=2)).isoformat()
    t2_date = (now - timedelta(hours=1)).isoformat()

    # Wątek 1: ostatni pisał zewnętrzny nadawca do użytkownika -> oczekuje_na_mnie
    store.save_mail_index(
        _make_record(
            thread_key="thread-1",
            subject="Projekt X",
            sender="anna@partner.com",
            recipients="me@corp.com",
            uid=1,
            date=t1_date,
            importance=8,
            summary="Anna pyta o akceptację kosztorysu.",
        )
    )

    # Wątek 2: użytkownik wysłał ostatnią wiadomość -> oczekuje_na_innych
    store.save_mail_index(
        _make_record(
            thread_key="thread-2",
            subject="Umowa Y",
            sender="anna@partner.com",
            recipients="me@corp.com",
            uid=2,
            date=(now - timedelta(hours=3)).isoformat(),
            importance=6,
        )
    )
    store.save_mail_index(
        _make_record(
            thread_key="thread-2",
            subject="Re: Umowa Y",
            sender="me@corp.com",
            recipients="anna@partner.com",
            uid=3,
            date=t2_date,
            importance=6,
            summary="Wysłałem podpisany aneks.",
        )
    )

    # Mock LLM
    def handler(request):
        body = json.loads(request.content)
        content_text = body["messages"][1]["content"]

        if "thread-1" in content_text or "Projekt X" in content_text:
            resp = {
                "title": "Kosztorys Projektu X",
                "why": "Anna czeka na akceptację budżetu.",
                "status": "oczekuje_na_mnie",
                "who_to_whom": ["Anna -> Użytkownik: zapytanie o budżet"],
            }
        else:
            resp = {
                "title": "Podpisanie umowy Y",
                "why": "Czekamy na ostateczną pieczątkę partnera.",
                "status": "oczekuje_na_innych",
                "who_to_whom": ["Użytkownik -> Anna: aneks wysłany"],
            }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = _llm_client(handler)
    digest = build_digest(store, client, config)

    assert len(digest.topics) == 2
    # Sortowanie: najpierw 'oczekuje_na_mnie'
    assert digest.topics[0].status == "oczekuje_na_mnie"
    assert digest.topics[0].title == "Kosztorys Projektu X"
    assert digest.topics[0].importance == 8
    assert digest.topics[0].mail_count == 1

    assert digest.topics[1].status == "oczekuje_na_innych"
    assert digest.topics[1].title == "Podpisanie umowy Y"
    assert digest.topics[1].mail_count == 2


def test_build_digest_caching():
    store = Store(":memory:")
    config = _make_config()

    store.save_mail_index(
        _make_record(
            thread_key="t-cached",
            subject="Oferta sprzętu",
            sender="sales@hardware.com",
            recipients="me@corp.com",
            uid=10,
            importance=7,
        )
    )

    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        resp = {
            "title": "Zakup komputerów",
            "why": "Oferta promocyjna od dostawcy.",
            "status": "oczekuje_na_mnie",
            "who_to_whom": ["sales -> me: oferta"],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = _llm_client(handler)

    # Pierwsze wywołanie -> pyta LLM i zapisuje do cache
    d1 = build_digest(store, client, config)
    assert call_count == 1
    assert d1.topics[0].title == "Zakup komputerów"

    # Drugie wywołanie -> pobiera z cache, LLM NIE jest pytany ponownie!
    d2 = build_digest(store, client, config)
    assert call_count == 1
    assert d2.topics[0].title == "Zakup komputerów"

    # Dodanie nowej wiadomości do wątku unieważnia cache (zmienia się mail_count / date)
    store.save_mail_index(
        _make_record(
            thread_key="t-cached",
            subject="Re: Oferta sprzętu",
            sender="me@corp.com",
            recipients="sales@hardware.com",
            uid=11,
            importance=7,
        )
    )

    d3 = build_digest(store, client, config)
    assert call_count == 2
    assert d3.topics[0].mail_count == 2


def test_build_digest_time_window():
    store = Store(":memory:")
    config = _make_config()
    now = datetime.now(timezone.utc)

    # Stary mail (sprzed 45 dni)
    old_date = (now - timedelta(days=45)).isoformat()
    store.save_mail_index(
        _make_record(
            thread_key="t-old",
            subject="Stara sprawa",
            sender="old@archive.com",
            recipients="me@corp.com",
            uid=20,
            date=old_date,
        )
    )

    # Nowy mail (sprzed 5 dni)
    new_date = (now - timedelta(days=5)).isoformat()
    store.save_mail_index(
        _make_record(
            thread_key="t-new",
            subject="Świeża sprawa",
            sender="new@recent.com",
            recipients="me@corp.com",
            uid=21,
            date=new_date,
        )
    )

    def handler(request):
        resp = {
            "title": "Świeża sprawa",
            "why": "Aktualny wątek",
            "status": "oczekuje_na_mnie",
            "who_to_whom": ["new -> me"],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = _llm_client(handler)

    # Domyślne okno 30 dni: tylko t-new
    digest = build_digest(store, client, config)
    assert len(digest.topics) == 1
    assert digest.topics[0].title == "Świeża sprawa"

    # Jawne okno 60 dni: oba wątki
    since_60 = (now - timedelta(days=60)).isoformat()
    digest_60 = build_digest(store, client, config, since=since_60)
    assert len(digest_60.topics) == 2


def test_build_digest_llm_error_tolerance():
    store = Store(":memory:")
    config = _make_config()

    store.save_mail_index(
        _make_record(
            thread_key="t-err",
            subject="Wątek z błędem",
            sender="err@domain.com",
            recipients="me@corp.com",
            uid=31,
            why="Przyczyna zapytania",
            summary="Streszczenie zapytania",
        )
    )
    store.save_mail_index(
        _make_record(
            thread_key="t-ok",
            subject="Wątek poprawny",
            sender="ok@domain.com",
            recipients="me@corp.com",
            uid=32,
        )
    )

    def handler(request):
        body = json.loads(request.content)
        content_text = body["messages"][1]["content"]
        if "t-err" in content_text or "Wątek z błędem" in content_text:
            return httpx.Response(500, text="Internal Server Error")

        resp = {
            "title": "Poprawny wątek",
            "why": "Wszystko działa",
            "status": "informacyjne",
            "who_to_whom": ["ok -> me"],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = _llm_client(handler)
    digest = build_digest(store, client, config)

    # Awaria LLM dla t-err nie zabiła reszty podsumowania
    assert len(digest.topics) == 2
    titles = [t.title for t in digest.topics]
    assert "Wątek z błędem" in titles
    assert "Poprawny wątek" in titles


def test_digest_status_progression_and_cache_invalidation():

    store = Store(":memory:")
    config = _make_config()
    now = datetime.now(timezone.utc)

    # 1. Przychodzący mail od Klienta -> oczekuje_na_mnie
    store.save_mail_index(
        _make_record(
            thread_key="thread-order",
            subject="Zamówienie 101",
            sender="klient@abc.com",
            recipients="me@corp.com",
            uid=1,
            date=(now - timedelta(hours=3)).isoformat(),
            direction="in",
        )
    )

    llm_calls = 0

    def handler(request):
        nonlocal llm_calls
        llm_calls += 1
        resp = {
            "title": "Zamówienie 101",
            "why": "Klient pyta o status zamówienia",
            "status": "oczekuje_na_mnie",
            "who_to_whom": ["klient -> Ty"],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = _llm_client(handler)

    d1 = build_digest(store, client, config)
    assert len(d1.topics) == 1
    assert d1.topics[0].status == "oczekuje_na_mnie"
    assert llm_calls == 1

    # Drugie wywołanie bez zmian w bazie -> korzysta z cache, brak nowego wywołania LLM
    d1_cached = build_digest(store, client, config)
    assert d1_cached.topics[0].status == "oczekuje_na_mnie"
    assert llm_calls == 1

    # 2. Użytkownik odpowiada (mail wychodzący w Sent, direction='out')
    store.save_mail_index(
        _make_record(
            thread_key="thread-order",
            subject="Re: Zamówienie 101",
            sender="me@corp.com",
            recipients="klient@abc.com",
            uid=2,
            date=(now - timedelta(hours=2)).isoformat(),
            direction="out",
        )
    )
    store.invalidate_topic_digest_cache("thread-order")

    d2 = build_digest(store, client, config)
    assert len(d2.topics) == 1
    # Status zmienił się na 'oczekuje_na_innych' na podstawie ostatniej wiadomości wychodzącej
    assert d2.topics[0].status == "oczekuje_na_innych"
    # LLM został ponownie wywołany ze względu na nową wiadomość
    assert llm_calls == 2

    # 3. Nowa odpowiedź przychodząca od Klienta -> powrót do 'oczekuje_na_mnie'
    store.save_mail_index(
        _make_record(
            thread_key="thread-order",
            subject="Re: Zamówienie 101",
            sender="klient@abc.com",
            recipients="me@corp.com",
            uid=3,
            date=(now - timedelta(hours=1)).isoformat(),
            direction="in",
        )
    )
    store.invalidate_topic_digest_cache("thread-order")

    d3 = build_digest(store, client, config)
    assert len(d3.topics) == 1
    assert d3.topics[0].status == "oczekuje_na_mnie"
    assert llm_calls == 3


def test_fallback_who_to_whom_bidirectional():
    from mailvoice.core.digest import _fallback_who_to_whom

    records = [
        _make_record(
            thread_key="th1",
            subject="Oferta",
            sender="anna@firm.com",
            recipients="me@corp.com",
            uid=1,
            direction="in",
        ),
        _make_record(
            thread_key="th1",
            subject="Re: Oferta",
            sender="me@corp.com",
            recipients="anna@firm.com",
            uid=2,
            direction="out",
        ),
    ]

    lines = _fallback_who_to_whom(records)
    assert len(lines) == 2
    assert "anna@firm.com -> Ty: Oferta" in lines[0]
    assert "Ty -> anna@firm.com: Oferta" in lines[1]
