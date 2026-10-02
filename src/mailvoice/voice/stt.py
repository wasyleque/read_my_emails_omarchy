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

    def __init__(
        self, model_size: str = "small", language: str | None = None, cue: bool = True
    ) -> None:
        self.model_size = model_size
        self.language = language
        self.cue = cue
        self._model = None

    def preload(self) -> None:
        """Ładuje model w tle (start aplikacji), by pierwsze nasłuchiwanie nie czekało."""
        import threading

        def _load() -> None:
            try:
                self._get_model()
            except VoiceUnavailable:
                pass  # błąd zgłosi pierwsze prawdziwe nasłuchiwanie

        threading.Thread(target=_load, name="whisper-preload", daemon=True).start()

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_size, device="auto", compute_type="int8")
            return self._model
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteka 'faster-whisper' nie jest zainstalowana.\n"
                "Zainstaluj obsługę rozpoznawania mowy poleceniem: pip install 'mailvoice[voice]'."
            ) from exc
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd ładowania modelu Whisper: {exc}") from exc

    def listen(self, timeout_s: float = 5.0) -> str | None:
        """Sygnał „mów”, nagrywa do ciszy po wypowiedzi (max timeout_s), transkrybuje Whisperem."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteki audio (sounddevice, numpy) nie są zainstalowane.\n"
                "Zainstaluj zależności poleceniem: pip install -e '.[voice]'."
            ) from exc

        model = self._get_model()
        try:
            if self.cue:
                _play_cue(sd, np)
            audio = _record_until_silence(sd, np, max_seconds=max(1.0, min(timeout_s, 12.0)))
        except VoiceUnavailable:
            raise
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd nagrywania z mikrofonu: {exc}") from exc
        if audio is None:
            return None  # nikt nie mówił
        try:
            segments, _ = model.transcribe(audio, language=self.language, vad_filter=True)
            text_parts = [segment.text.strip() for segment in segments]
            return " ".join(text_parts).strip() or None
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd transkrypcji Whisper: {exc}") from exc


SAMPLE_RATE = 16000
CHUNK_S = 0.1
DEAD_MIC_PEAK = 1e-4


class EndpointDetector:
    """Wykrywa początek i koniec wypowiedzi po energii (RMS) kolejnych krótkich fragmentów."""

    def __init__(self, silence_s: float = 0.9, min_threshold: float = 0.02, calib_chunks: int = 3):
        self.silence_chunks = max(1, round(silence_s / CHUNK_S))
        self.min_threshold = min_threshold
        self.calib_chunks = calib_chunks
        self._calib: list[float] = []
        self.threshold: float | None = None
        self.started = False
        self._quiet = 0

    def feed(self, rms: float) -> bool:
        """True, gdy wypowiedź się skończyła (była mowa, potem wystarczająco długa cisza)."""
        if self.threshold is None:
            self._calib.append(rms)
            if len(self._calib) >= self.calib_chunks:
                noise = sorted(self._calib)[len(self._calib) // 2]
                self.threshold = max(noise * 3.0, self.min_threshold)
            return False
        if rms >= self.threshold:
            self.started = True
            self._quiet = 0
            return False
        if self.started:
            self._quiet += 1
            return self._quiet >= self.silence_chunks
        return False


def _play_cue(sd, np) -> None:
    """Krótki sygnał „teraz mów” (cichy, żeby nie zagłuszać mikrofonu)."""
    t = np.linspace(0, 0.12, int(0.12 * 22050), endpoint=False)
    sd.play((0.2 * np.sin(2 * np.pi * 880 * t)).astype("float32"), samplerate=22050)
    sd.wait()


def _record_until_silence(sd, np, max_seconds: float):
    """Nagrywa do ciszy po wypowiedzi. None = nikt nie mówił; martwy mikrofon = VoiceUnavailable."""
    detector = EndpointDetector()
    frames = []
    chunk = int(SAMPLE_RATE * CHUNK_S)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        for _ in range(int(max_seconds / CHUNK_S)):
            data, _overflow = stream.read(chunk)
            x = data.flatten()
            frames.append(x)
            if detector.feed(float(np.sqrt(np.mean(x**2)))):
                break
    audio = np.concatenate(frames)
    if float(np.max(np.abs(audio))) < DEAD_MIC_PEAK:
        raise VoiceUnavailable(
            "Mikrofon nie przekazuje dźwięku. Sprawdź, czy wejście nie jest wyciszone ani "
            "ustawione na 0% (np. polecenie: wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.5)."
        )
    return audio if detector.started else None
