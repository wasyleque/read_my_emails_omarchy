"""Testy syntezatora mowy opartego na głosach Windows (WindowsSapiSpeaker)."""

import pytest

from mailvoice.voice.tts import VoiceUnavailable, WindowsSapiSpeaker


def test_set_volume_clamps_to_range():
    s = WindowsSapiSpeaker()
    s.set_volume(5.0)
    assert s.volume == 2.0
    s.set_volume(-1.0)
    assert s.volume == 0.0
    s.set_volume(0.75)
    assert s.volume == 0.75


def test_speak_raises_on_non_windows(monkeypatch):
    """Na systemie innym niż Windows głos SAPI jest niedostępny — czytelny wyjątek, nie crash."""
    monkeypatch.setattr("mailvoice.voice.tts.sys.platform", "linux")
    s = WindowsSapiSpeaker()
    with pytest.raises(VoiceUnavailable):
        s.speak("test", "pl")


def test_default_voices_are_polish_and_english():
    s = WindowsSapiSpeaker()
    assert "Paulina" in s.pl_voice
    assert "Zira" in s.en_voice
