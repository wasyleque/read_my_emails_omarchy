"""PiperSpeaker: znajdowanie programu i modelu głosu oraz czytelne błędy (bez dźwięku)."""

import sys

import pytest

from mailvoice.voice import tts
from mailvoice.voice.tts import PiperSpeaker, VoiceUnavailable


def test_model_found_by_name_in_voices_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "voices_dir", lambda: tmp_path)
    (tmp_path / "pl_PL-darkman-medium.onnx").write_bytes(b"x")
    assert (
        PiperSpeaker()._model_path("pl_PL-darkman-medium") == tmp_path / "pl_PL-darkman-medium.onnx"
    )


def test_missing_voice_tells_exact_command(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "voices_dir", lambda: tmp_path)
    with pytest.raises(VoiceUnavailable) as exc:
        PiperSpeaker()._model_path("en_US-lessac-medium")
    assert "piper.download_voices" in str(exc.value) and "en_US-lessac-medium" in str(exc.value)


def test_piper_found_next_to_interpreter(tmp_path, monkeypatch):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "piper").write_text("#!/bin/sh\n")
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))
    assert PiperSpeaker()._find_piper() == str(fake_bin / "piper")


def test_missing_piper_message_is_actionable(monkeypatch):
    monkeypatch.setattr(PiperSpeaker, "_find_piper", lambda self: None)
    with pytest.raises(VoiceUnavailable) as exc:
        PiperSpeaker()._verify_availability()
    assert "pip install piper-tts" in str(exc.value)


def test_sample_rate_read_from_model_config(tmp_path):
    model = tmp_path / "v.onnx"
    (tmp_path / "v.onnx.json").write_text('{"audio": {"sample_rate": 16000}}')
    assert PiperSpeaker._sample_rate(model) == 16000
    assert PiperSpeaker._sample_rate(tmp_path / "brak.onnx") == 22050
