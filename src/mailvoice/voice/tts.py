"""Moduł syntezy mowy (TTS - Text To Speech).

Obsługuje protokół Speaker, implementację PiperSpeaker oraz FakeSpeaker do testów.
"""

import shutil
import subprocess
from typing import Protocol


class VoiceUnavailable(Exception):
    """Wyjątek rzucany, gdy silnik syntezy lub rozpoznawania głosu jest niedostępny."""

    pass


class Speaker(Protocol):
    """Protokół syntezatora mowy (TTS)."""

    def speak(self, text: str, lang: str = "pl") -> None:
        """Odczytuje podany tekst na głos w wybranym języku (pl/en)."""
        ...

    def stop(self) -> None:
        """Zatrzymuje bieżące odtwarzanie mowy."""
        ...

    def set_volume(self, volume: float) -> None:
        """Ustawia poziom głośności (np. 0.0 - 2.0)."""
        ...


class FakeSpeaker:
    """Atrapa syntezatora mowy przechowująca wypowiedziane kwestie w pamięci."""

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []
        self.is_speaking: bool = False
        self.volume: float = 1.0

    def speak(self, text: str, lang: str = "pl") -> None:
        self.is_speaking = True
        self.spoken.append((text, lang))
        self.is_speaking = False

    def stop(self) -> None:
        self.is_speaking = False

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(2.0, volume))


class PiperSpeaker:
    """Syntezator mowy oparty na zewnętrznym programie Piper i bibliotece sounddevice."""

    def __init__(
        self,
        piper_binary: str = "piper",
        pl_model: str = "pl_PL-darkman-medium",
        en_model: str = "en_US-lessac-medium",
    ) -> None:
        self.piper_binary = piper_binary
        self.pl_model = pl_model
        self.en_model = en_model
        self.volume: float = 1.0
        self._current_process: subprocess.Popen | None = None

    def _verify_availability(self) -> None:
        if not shutil.which(self.piper_binary):
            raise VoiceUnavailable(
                "Program syntezy mowy 'piper' nie został znaleziony w systemie.\n"
                "Aby korzystać z syntezy mowy, pobierz program Piper ze strony:\n"
                "https://github.com/rhasspy/piper/releases\n"
                "i umieść plik wykonywalny 'piper' w zmiennej środowiskowej PATH."
            )
        try:
            import sounddevice  # noqa: F401
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteka 'sounddevice' nie jest zainstalowana.\n"
                "Zainstaluj obsługę audio poleceniem: pip install 'mailvoice[voice]'."
            ) from exc

    def speak(self, text: str, lang: str = "pl") -> None:
        self._verify_availability()
        model = self.en_model if lang.lower().startswith("en") else self.pl_model

        # Uruchomienie syntezy Piper i strumieniowanie do odtwarzacza
        try:
            # Piper generuje surowe próbki WAV na stdout
            self._current_process = subprocess.Popen(
                [self.piper_binary, "--model", model, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw_audio, _ = self._current_process.communicate(input=text.encode("utf-8"))

            if raw_audio:
                import numpy as np
                import sounddevice as sd

                # Piper domyślnie generuje 16-bit PCM mono 22050Hz
                audio_data = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
                if self.volume != 1.0:
                    audio_data = audio_data * self.volume
                sd.play(audio_data, samplerate=22050)
                sd.wait()
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd podczas syntezy mowy Piper: {exc}") from exc
        finally:
            self._current_process = None

    def stop(self) -> None:
        if self._current_process is not None:
            try:
                self._current_process.terminate()
            except Exception:
                pass
            self._current_process = None
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(2.0, volume))
