"""Testy szablonów dostawców poczty IMAP."""

from mailvoice.core.providers import get_provider_by_id, get_providers


def test_get_providers_list():
    providers = get_providers()
    assert len(providers) >= 7
    ids = [p.provider_id for p in providers]
    assert "gmail" in ids
    assert "outlook" in ids
    assert "wp" in ids
    assert "onet" in ids
    assert "o2" in ids
    assert "interia" in ids
    assert "other" in ids


def test_gmail_provider_configuration():
    gmail = get_provider_by_id("gmail")
    assert gmail.host == "imap.gmail.com"
    assert gmail.port == 993
    assert gmail.use_ssl is True
    assert "[Gmail]" in gmail.sent_folder
    assert "Hasła do aplikacji" in gmail.help_text_pl


def test_unknown_provider_fallback():
    fallback = get_provider_by_id("nieznany_dostawca")
    assert fallback.provider_id == "other"
    assert fallback.host == ""
