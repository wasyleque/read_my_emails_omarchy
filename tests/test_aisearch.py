"""Testy modułu wyszukiwania maili AI (core/aisearch.py)."""

import json
from datetime import datetime, timedelta, timezone

import httpx

from mailvoice.core.aisearch import MailRef, SearchHit, search
from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import OllamaConfig
from mailvoice.core.store import MailIndexRecord, Store


def _make_record(
    uid: int,
    sender: str,
    subject: str,
    summary: str,
    why: str = "Sprawa bieżąca",
    date: str | None = None,
) -> MailIndexRecord:
    dt = date or datetime.now(timezone.utc).isoformat()
    return MailIndexRecord(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=uid,
        message_id=f"<m{uid}@test.pl>",
        thread_key=f"t{uid}",
        date=dt,
        sender=sender,
        recipients="me@corp.com",
        subject=subject,
        importance=8,
        why=why,
        summary=summary,
    )


def test_search_no_results():
    store = Store(":memory:")

    def handler(request):
        return httpx.Response(200, json={"message": {"content": "{}"}})

    client = OllamaClient(OllamaConfig(), transport=httpx.MockTransport(handler))
    results = search(store, client, query="faktura za prąd")
    assert results == []


def test_search_ranking_and_confidence():
    store = Store(":memory:")
    # 1. Kowalski - faktura za remont
    store.save_mail_index(
        _make_record(
            uid=101,
            sender="Piotr Kowalski <kowalski@budowa.pl>",
            subject="Faktura VAT 45/2026 za remont biura",
            summary="Załączam fakturę za materiały i robociznę.",
            why="Płatność za remont",
        )
    )
    # 2. Nowak - raport kwartalny
    store.save_mail_index(
        _make_record(
            uid=102,
            sender="Jan Nowak <nowak@firma.pl>",
            subject="Raport kwartalny sprzedaży",
            summary="Zestawienie wyników sprzedaży za Q3.",
        )
    )

    def handler(request):
        body = json.loads(request.content)
        content_text = body["messages"][1]["content"]

        # Krok 2: Re-ranking
        if "Kandydaci wiadomości:" in content_text:
            resp = {
                "ranked_uids": [
                    {
                        "uid": 101,
                        "score": 0.95,
                        "confidence": "wysoka",
                        "why_probable": "Zgadzają się nadawca oraz faktura za remont.",
                    }
                ]
            }
            return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

        # Krok 1: Rozszerzenie zapytania
        if "Zapytanie użytkownika: ten mail od Kowalskiego" in content_text:
            resp = {
                "senders": ["Kowalski", "kowalski@budowa.pl"],
                "keywords": ["faktura", "remont", "biura"],
            }
            return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

        return httpx.Response(200, json={"message": {"content": "{}"}})

    client = OllamaClient(OllamaConfig(), transport=httpx.MockTransport(handler))

    results = search(store, client, query="ten mail od Kowalskiego o fakturze za remont")

    assert len(results) == 1
    hit = results[0]
    assert isinstance(hit, SearchHit)
    assert isinstance(hit.mail_ref, MailRef)
    assert hit.mail_ref.uid == 101
    assert hit.score == 0.95
    assert hit.confidence == "wysoka"
    assert "remont" in hit.why_probable


def test_search_date_filtering():
    store = Store(":memory:")
    now = datetime.now(timezone.utc)

    # Stary mail (sprzed 50 dni)
    old_dt = (now - timedelta(days=50)).isoformat()
    store.save_mail_index(
        _make_record(
            uid=201,
            sender="Kowalski <k@test.pl>",
            subject="Faktura stara",
            summary="Faktura z zeszłego miesiąca.",
            date=old_dt,
        )
    )

    def handler(request):
        # query expansion
        resp = {"senders": ["Kowalski"], "keywords": ["faktura"]}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    client = OllamaClient(OllamaConfig(), transport=httpx.MockTransport(handler))

    # W oknie 30 dni nic nie powinno być znalezione
    res_30 = search(store, client, query="faktura Kowalski", days=30)
    assert len(res_30) == 0

    # W oknie 60 dni mail powinien zostać znaleziony
    res_60 = search(store, client, query="faktura Kowalski", days=60)
    assert len(res_60) == 1
    assert res_60[0].mail_ref.uid == 201


def test_search_llm_error_degradation_to_fts():
    store = Store(":memory:")
    store.save_mail_index(
        _make_record(
            uid=301,
            sender="Piotr Kowalski <kowalski@budowa.pl>",
            subject="Faktura remontowa",
            summary="Rozliczenie prac malarskich.",
        )
    )

    def handler(request):
        # Symulacja awarii serwera Ollama
        return httpx.Response(500, text="Ollama offline")

    client = OllamaClient(OllamaConfig(), transport=httpx.MockTransport(handler))

    # Nawet przy awarii LLM wyszukiwanie nie rzuca wyjątku, degradując do FTS
    results = search(store, client, query="faktura remontowa")
    assert len(results) == 1
    assert results[0].mail_ref.uid == 301
    assert results[0].confidence in ("wysoka", "średnia")
