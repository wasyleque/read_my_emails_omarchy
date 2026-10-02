"""Gdzie odtwarzać powiadomienia głosowe + gwarancja, że zapis Ustawień niczego nie resetuje."""

import dataclasses

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from mailvoice.core.config import AccountConfig, AppConfig, ServerConfig
from mailvoice.core.voice_routing import VOICE_OUTPUT_CHOICES, computer_should_speak
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker


@pytest.mark.parametrize(
    "mode, phones, expected",
    [
        ("auto", 0, True),  # brak telefonu -> czyta komputer
        ("auto", 1, False),  # telefon połączony -> milczy komputer
        ("computer", 0, True),
        ("computer", 2, True),
        ("phone", 0, False),
        ("phone", 1, False),
        ("both", 0, True),
        ("both", 1, True),
    ],
)
def test_computer_should_speak_matrix(mode, phones, expected):
    assert computer_should_speak(mode, phones) is expected


def test_choices_cover_all_modes():
    assert set(VOICE_OUTPUT_CHOICES) == {"auto", "computer", "phone", "both"}


def test_config_default_roundtrip_and_validation():
    assert AppConfig().voice_output == "auto"
    cfg = AppConfig.from_dict({"voice_output": "phone"})
    assert cfg.voice_output == "phone"
    assert AppConfig.from_dict(cfg.to_dict()).voice_output == "phone"
    with pytest.raises(ValueError):
        AppConfig.from_dict({"voice_output": "radio"})


class _Secrets:
    def get(self, a):
        return None

    def set(self, a, s):
        pass

    def delete(self, a):
        pass


def test_saving_settings_without_changes_resets_nothing(tmp_path, monkeypatch):
    """Regresja: zapis Ustawień gubił pola, których nie pokazuje (np. `server`)."""
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    original = AppConfig(
        accounts=[AccountConfig(name="a@x.pl", host="imap.x.pl", username="a@x.pl")],
        analysis_prompt="coś ważnego",
        vip_senders=["@vip.pl"],
        keywords=["umowa"],
        blocked_senders=["spam@"],
        interval_minutes=15,
        notify_mode="ask",
        voice_output="phone",
        beep_repeat_minutes=7,
        ask_retry_minutes=20,
        importance_threshold=8,
        backlog_days=14,
        digest_days=45,
        index_retention_days=120,
        my_addresses=["ja@x.pl"],
        language="en",
        server=ServerConfig(enabled=True, port=9001, bind="192.168.1.5", max_devices=3),
    )
    saved = []
    dlg = SettingsDialog(
        config=original,
        config_path=tmp_path / "c.json",
        secret_store=_Secrets(),
        speaker=FakeSpeaker(),
        on_config_saved=saved.append,
    )
    dlg._on_save()
    assert saved, "zapis nie wywołał on_config_saved"
    after = saved[0]
    changed = {
        f.name
        for f in dataclasses.fields(AppConfig)
        if getattr(after, f.name) != getattr(original, f.name)
    }
    # pole `ollama` może zmienić się przez wykrywanie modeli; reszta musi zostać nietknięta
    assert changed <= {"ollama"}, f"zapis zresetował pola: {sorted(changed)}"
    assert after.voice_output == "phone"
    assert after.server.port == 9001
