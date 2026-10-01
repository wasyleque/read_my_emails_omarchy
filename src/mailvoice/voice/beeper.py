"""Moduł sygnalizacji dźwiękowej (beeper)."""

from typing import Protocol

from mailvoice.voice.tts import VoiceUnavailable


class Beeper(Protocol):
    """Protokół emitera sygnału dźwiękowego."""

    def beep(self) -> None:
        """Odtwarza krótki sygnał dźwiękowy (beep)."""
        ...


class FakeBeeper:
    """Atrapa sygnalizatora dźwiękowego zliczająca wywołania w pamięci."""

    def __init__(self) -> None:
        self.beeps: int = 0

    def beep(self) -> None:
        self.beeps += 1


class SounddeviceBeeper:
    """Sygnalizator dźwiękowy generujący prosty ton sinusoidalny przez sounddevice."""

    def __init__(self, frequency: float = 880.0, duration: float = 0.25) -> None:
        self.frequency = frequency
        self.duration = duration

    def beep(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            sample_rate = 44100
            t = np.linspace(0, self.duration, int(sample_rate * self.duration), False)
            tone = 0.5 * np.sin(2 * np.pi * self.frequency * t).astype(np.float32)
            sd.play(tone, samplerate=sample_rate)
            sd.wait()
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteka audio 'sounddevice' lub 'numpy' nie jest dostępna. "
                "Zainstaluj obsługę głosu poleceniem: pip install 'mailvoice[voice]'."
            ) from exc
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd odtwarzania sygnału beep: {exc}") from exc
