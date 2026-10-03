"""Moduł syntezy mowy (TTS - Text To Speech).

Obsługuje protokół Speaker, implementację PiperSpeaker oraz FakeSpeaker do testów.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

import platformdirs


class VoiceUnavailable(Exception):
    """Wyjątek rzucany, gdy silnik syntezy lub rozpoznawania głosu jest niedostępny."""

    pass


def voices_dir() -> Path:
    """Katalog z modelami głosów Piper (poza repozytorium, w danych użytkownika)."""
    return Path(platformdirs.user_data_dir("mailvoice")) / "voices"


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


class WindowsSapiSpeaker:
    """Syntezator mowy oparty na wbudowanych głosach Windows (System.Speech przez PowerShell).

    Nie wymaga modeli Piper ani sounddevice — używa głosów zainstalowanych w systemie
    (np. „Microsoft Paulina Desktop” dla polskiego, „Microsoft Zira Desktop” dla angielskiego).
    """

    def __init__(
        self,
        pl_voice: str = "Microsoft Paulina Desktop",
        en_voice: str = "Microsoft Zira Desktop",
    ) -> None:
        self.pl_voice = pl_voice
        self.en_voice = en_voice
        self.volume: float = 1.0
        self._current_process: subprocess.Popen | None = None

    @staticmethod
    def _powershell() -> str | None:
        return shutil.which("powershell") or shutil.which("pwsh")

    def _verify_availability(self) -> str:
        if sys.platform != "win32":
            raise VoiceUnavailable("Głosy Windows (SAPI) są dostępne tylko w systemie Windows.")
        ps = self._powershell()
        if not ps:
            raise VoiceUnavailable("Nie znaleziono programu PowerShell do odtworzenia mowy.")
        return ps

    def speak(self, text: str, lang: str = "pl") -> None:
        ps = self._verify_availability()
        voice = self.en_voice if lang.lower().startswith("en") else self.pl_voice
        sapi_volume = max(0, min(100, round(self.volume * 100)))
        # Nazwa głosu i głośność pochodzą od nas (nie od treści maila) — brak ryzyka wstrzyknięcia.
        # Treść maila trafia wyłącznie przez stdin i nigdy nie jest wklejana do polecenia.
        script = (
            "[Console]::InputEncoding=[Text.Encoding]::UTF8;"
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"try{{$s.SelectVoice('{voice}')}}catch{{}};"
            f"$s.Volume={sapi_volume};"
            "$s.Speak([Console]::In.ReadToEnd())"
        )
        try:
            self._current_process = subprocess.Popen(
                [ps, "-NoProfile", "-NonInteractive", "-Command", script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, err = self._current_process.communicate(input=text.encode("utf-8"))
            code = self._current_process.returncode
            if code not in (0, None) and err:
                tail = err.decode("utf-8", "replace").strip().splitlines()[-1:]
                raise VoiceUnavailable(f"Głos Windows nie odtworzył mowy: {' '.join(tail)}")
        except VoiceUnavailable:
            raise
        except Exception as exc:
            raise VoiceUnavailable(f"Błąd podczas syntezy mowy (Windows): {exc}") from exc
        finally:
            self._current_process = None

    def stop(self) -> None:
        if self._current_process is not None:
            try:
                self._current_process.terminate()
            except Exception:
                pass
            self._current_process = None

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

    def _find_piper(self) -> str | None:
        """Szuka programu piper w PATH oraz obok interpretera (środowisko venv bez aktywacji)."""
        found = shutil.which(self.piper_binary)
        if found:
            return found
        sibling = Path(sys.executable).parent / self.piper_binary
        return str(sibling) if sibling.exists() else None

    def _verify_availability(self) -> str:
        piper = self._find_piper()
        if not piper:
            raise VoiceUnavailable(
                "Program syntezy mowy 'piper' nie został znaleziony.\n"
                "Najprościej: w środowisku aplikacji uruchom  pip install piper-tts\n"
                "(albo pobierz program ze strony projektu Piper i dodaj go do PATH)."
            )
        try:
            import sounddevice  # noqa: F401
        except ImportError as exc:
            raise VoiceUnavailable(
                "Biblioteka 'sounddevice' nie jest zainstalowana.\n"
                "Zainstaluj obsługę audio poleceniem: pip install -e '.[voice]'."
            ) from exc
        return piper

    def _model_path(self, name: str) -> Path:
        """Pełna ścieżka do modelu głosu; Piper nie znajduje głosu po samej nazwie."""
        direct = Path(name)
        if direct.suffix == ".onnx" and direct.exists():
            return direct
        candidate = voices_dir() / f"{name}.onnx"
        if not candidate.exists():
            raise VoiceUnavailable(
                f"Brak głosu '{name}'. Pobierz go jednym poleceniem:\n"
                f"  python -m piper.download_voices --download-dir {voices_dir()} {name}"
            )
        return candidate

    @staticmethod
    def _sample_rate(model: Path) -> int:
        try:
            cfg = json.loads(Path(f"{model}.json").read_text(encoding="utf-8"))
            return int(cfg.get("audio", {}).get("sample_rate", 22050))
        except (OSError, ValueError):
            return 22050

    def _synthesize(self, piper: str, model: Path, text: str) -> bytes:
        """Uruchamia Piper i zwraca surowe próbki 16-bit PCM mono (bez odtwarzania)."""
        self._current_process = subprocess.Popen(
            [piper, "--model", str(model), "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        raw_audio, err = self._current_process.communicate(input=text.encode("utf-8"))
        if not raw_audio and err:
            tail = err.decode("utf-8", "replace").strip().splitlines()[-1:]
            raise VoiceUnavailable(f"Piper nie wygenerował dźwięku: {' '.join(tail)}")
        return raw_audio

    def speak(self, text: str, lang: str = "pl") -> None:
        piper = self._verify_availability()
        model = self._model_path(self.en_model if lang.lower().startswith("en") else self.pl_model)
        try:
            raw_audio = self._synthesize(piper, model, text)
            if raw_audio:
                import numpy as np
                import sounddevice as sd

                audio_data = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
                if self.volume != 1.0:
                    audio_data = audio_data * self.volume
                sd.play(audio_data, samplerate=self._sample_rate(model))
                sd.wait()
        except VoiceUnavailable:
            raise
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
