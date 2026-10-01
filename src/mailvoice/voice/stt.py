"""Moduł rozpoznawania mowy (STT - Speech To Text).

Obsługuje protokół Listener, implementację WhisperListener oraz FakeListener do testów.
"""

from collections import deque
from typing import Protocol

from mailvoice.voice.tts import VoiceUnavailable


class Listener(Protocol):
    """Protokół modułu nasłuchiwania i rozpoznawania mowy użytkownika."""

    def listen(self, timeout_s: float = 5.0) -> str | None:
        """Nasłuchuje wypowiedzi przez zadany czas i zwraca rozpoznany tekst lub None."""
        ...


class FakeListener:
    """Atrapa modułu rozpoznawania mowy z kolejką przygotowanych odpowiedzi."""

    def __init__(self, responses: list[str | None] | None = None) -> None:
        self.responses: deque[str | None] = deque(responses or [])

    def push_response(self, text: str | None) -> None:
        """Dodaje odpowiedź na koniec kolejki."""
        self.responses.append(text)

    def listen(self, timeout_s: float = 5.0) -> str | None:
        """Pobiera kolejną odpowiedź z kolejki lub zwraca None, jeśli pusta."""
        if self.responses:
            return self.responses.popleft()
        return None


class WhisperListener:
    """Implementacja rozpoznawania mowy oparta na bibliotece faster-whisper z VAD."""

    def __init__(self, model_size: str = "small", language: str | None = None) -> None:
        self.model_size = model_size
        self.language = language
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_size, device="auto", compute_type="default")
            return self._model
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteka 'faster-whisper' nie jest zainstalowana.\n"
                "Zainstaluj obsługę rozpoznawania mowy poleceniem: pip install 'mailvoice[voice]'."
            ) from exc
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd ładowania modelu Whisper: {exc}") from exc

    def listen(self, timeout_s: float = 5.0) -> str | None:
        """Nagrywa dźwięk z mikrofonu do momentu ciszy i transkrybuje model Whisper."""
        try:
            import numpy as np  # noqa: F401
            import sounddevice as sd  # noqa: F401
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteki audio (sounddevice, numpy) nie są zainstalowane.\n"
                "Zainstaluj zależności poleceniem: pip install 'mailvoice[voice]'."
            ) from exc

        model = self._get_model()
        # W środowisku bez podłączonego fizycznego mikrofonu zwracamy None lub transkrypcję
        try:
            sample_rate = 16000
            duration = min(timeout_s, 5.0)
            audio = sd.rec(
                int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype="float32"
            )
            sd.wait()
            audio_flat = audio.flatten()
            if np.max(np.abs(audio_flat)) < 0.01:
                # Cisza
                return None

            segments, _ = model.transcribe(audio_flat, language=self.language, vad_filter=True)
            text_parts = [segment.text.strip() for segment in segments]
            return " ".join(text_parts).strip() or None
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd nagrywania lub transkrypcji Whisper: {exc}") from exc
