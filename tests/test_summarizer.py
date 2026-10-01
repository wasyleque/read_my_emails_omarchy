"""Testy modułu streszczania wiadomości (summarizer.py)."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from mailvoice.core.analyzer import AnalyzerError, OllamaClient
from mailvoice.core.config import AppConfig, OllamaConfig
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.summarizer import limit_sentences, split_sentences, summarize


def test_split_sentences_with_abbreviations():
    text = (
        "Dr. Kowalski przyjechał do Warszawy. "
        "Spotkanie odbędzie się o godz. 12:00. "
        "Będziemy omawiać projekt np. nowy system. "
        "Proszę o potwierdzenie. Dziękuję."
    )
    sentences = split_sentences(text)
    assert len(sentences) == 5
    assert sentences[0] == "Dr. Kowalski przyjechał do Warszawy."
    assert sentences[1] == "Spotkanie odbędzie się o godz. 12:00."
    assert sentences[2] == "Będziemy omawiać projekt np. nowy system."
    assert sentences[3] == "Proszę o potwierdzenie."
    assert sentences[4] == "Dziękuję."


def test_limit_sentences():
    text = (
        "Pierwsze zdanie. Drugie zdanie! Trzecie zdanie? "
        "Czwarte zdanie. Piąte zdanie. Szóste zdanie."
    )
    limited = limit_sentences(text, max_sentences=4)
    expected = "Pierwsze zdanie. Drugie zdanie! Trzecie zdanie? Czwarte zdanie."
    assert limited == expected


def test_limit_sentences_short():
    text = "Tylko dwa zdania. Drugie zdanie."
    assert limit_sentences(text, max_sentences=4) == text


def test_summarize_empty_body():
    cfg = OllamaConfig()
    client = OllamaClient(cfg)
    mail_pl = ParsedMail(
        message_id="<test@example.com>",
        sender="sender@example.com",
        subject="Faktura VAT",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="   ",
    )

    summary_pl = summarize(client, cfg, mail_pl, language="pl")
    assert "Faktura VAT" in summary_pl
    assert "Wiadomość bez treści" in summary_pl

    mail_en = ParsedMail(
        message_id="<test@example.com>",
        sender="sender@example.com",
        subject="Invoice",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="",
    )
    summary_en = summarize(client, cfg, mail_en, language="en")
    assert "Invoice" in summary_en
    assert "No message body" in summary_en


def test_summarize_with_mock_transport():
    cfg = AppConfig(
        ollama=OllamaConfig(
            lan_url="http://lan:11434",
            local_url="http://local:11434",
            model="qwen3:8b",
            polish_model="bielik:11b",
            prefer="lan",
        )
    )

    long_response = (
        "Klient pyta o harmonogram prac. "
        "Wymagane jest przesłanie wyceny do piątku. "
        "Spotkanie zaplanowano na poniedziałek. "
        "Dr. Nowak przygotuje dokumentację. "
        "To jest piąte nadmiarowe zdanie, które powinno zostać odcięte."
    )

    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        assert data["model"] == "bielik:11b"
        return httpx.Response(
            200,
            json={"message": {"content": long_response}},
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient(cfg.ollama, transport=transport)

    mail = ParsedMail(
        message_id="<123@domain.com>",
        sender="klient@firma.pl",
        subject="Nowy projekt",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="Dzień dobry, przesyłam szczegóły nowego projektu...",
    )

    summary = summarize(client, cfg, mail, language="pl")
    # Powinno być maksymalnie 4 zdania (piąte odcięte)
    sentences = split_sentences(summary)
    assert len(sentences) == 4
    assert "Dr. Nowak przygotuje dokumentację." in summary
    assert "nadmiarowe zdanie" not in summary


def test_summarize_failover():
    cfg = OllamaConfig(
        lan_url="http://lan:11434",
        local_url="http://local:11434",
        prefer="lan",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "lan:11434" in str(request.url):
            raise httpx.ConnectError("LAN niedostępny")
        return httpx.Response(
            200,
            json={"message": {"content": "Streszczenie z serwera lokalnego."}},
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient(cfg, transport=transport)

    mail = ParsedMail(
        message_id="<test@domain.com>",
        sender="sender@example.com",
        subject="Temat",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="Treść wiadomości do streszczenia.",
    )

    summary = summarize(client, cfg, mail, language="pl")
    assert summary == "Streszczenie z serwera lokalnego."


def test_summarize_all_endpoints_fail():
    cfg = OllamaConfig(
        lan_url="http://lan:11434",
        local_url="http://local:11434",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Błąd sieci")

    transport = httpx.MockTransport(handler)
    client = OllamaClient(cfg, transport=transport)

    mail = ParsedMail(
        message_id="<test@domain.com>",
        sender="sender@example.com",
        subject="Temat",
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="Treść wiadomości.",
    )

    with pytest.raises(AnalyzerError):
        summarize(client, cfg, mail, language="pl")
