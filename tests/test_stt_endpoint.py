"""Wykrywanie końca wypowiedzi i martwego mikrofonu (bez prawdziwego audio)."""

import numpy as np
import pytest

from mailvoice.voice import stt
from mailvoice.voice.stt import EndpointDetector
from mailvoice.voice.tts import VoiceUnavailable


def _run(levels):
    det = EndpointDetector()
    for i, rms in enumerate(levels):
        if det.feed(rms):
            return i, det
    return None, det


def test_stops_after_silence_following_speech():
    levels = [0.005] * 3 + [0.2] * 5 + [0.004] * 20
    stop, det = _run(levels)
    assert det.started and stop is not None
    assert stop == 3 + 5 + det.silence_chunks - 1  # dokładnie po wymaganej ciszy


def test_never_stops_without_speech():
    stop, det = _run([0.004] * 50)
    assert stop is None and not det.started


def test_noisy_room_raises_threshold():
    det = EndpointDetector()
    for _ in range(3):
        det.feed(0.05)  # głośne tło
    assert det.threshold >= 0.15


class _FakeStream:
    def __init__(self, level):
        self.level = level

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return np.full((n, 1), self.level, dtype="float32"), False


class _FakeSd:
    def __init__(self, level):
        self.level = level

    def InputStream(self, **kw):  # noqa: N802
        return _FakeStream(self.level)


def test_dead_microphone_raises_actionable_error():
    with pytest.raises(VoiceUnavailable) as exc:
        stt._record_until_silence(_FakeSd(0.0), np, max_seconds=1.0)
    assert "Mikrofon nie przekazuje dźwięku" in str(exc.value) and "0%" in str(exc.value)


def test_quiet_room_returns_none_not_error():
    assert stt._record_until_silence(_FakeSd(0.001), np, max_seconds=1.0) is None
