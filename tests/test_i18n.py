"""Testy tłumaczeń i18n oraz spójności kluczy między językami."""

from mailvoice.ui.i18n import _TRANSLATIONS, set_language, tr


def test_i18n_keys_parity():
    """Weryfikuje, że słowniki PL i EN posiadają dokładnie ten sam zestaw kluczy."""
    pl_keys = set(_TRANSLATIONS["pl"].keys())
    en_keys = set(_TRANSLATIONS["en"].keys())

    missing_in_en = pl_keys - en_keys
    missing_in_pl = en_keys - pl_keys

    assert not missing_in_en, f"Klucze brakujące w słowniku angielskim: {missing_in_en}"
    assert not missing_in_pl, f"Klucze brakujące w słowniku polskim: {missing_in_pl}"
    assert len(pl_keys) == len(en_keys)


def test_tr_language_switch():
    set_language("pl")
    assert tr("app_title") == "MailVoice"
    assert "Witaj" in tr("step1_title")

    set_language("en")
    assert tr("app_title") == "MailVoice"
    assert "Welcome" in tr("step1_title")


def test_tr_with_formatting():
    msg_pl = tr("backlog_dialog_msg", lang="pl", count=5)
    assert "5 starszych" in msg_pl

    msg_en = tr("backlog_dialog_msg", lang="en", count=3)
    assert "3 older" in msg_en


def test_tr_fallback_unknown_key():
    set_language("pl")
    assert tr("non_existent_key_123") == "non_existent_key_123"
