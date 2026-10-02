"""Statyczne testy bezpieczeństwa kodu (AST) oraz weryfikacja izolacji komend głosowych."""

import ast
from pathlib import Path

from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import ProcessedMail
from mailvoice.voice.dialog import VoiceDialog
from mailvoice.voice.stt import Listener
from mailvoice.voice.tts import Speaker


def test_static_ast_forbidden_security_patterns():
    """Weryfikuje, że w kodzie źródłowym src/ nie występują niebezpieczne wzorce.

    Zabronione:
    - webbrowser
    - QDesktopServices.openUrl
    - setOpenExternalLinks
    - QTextBrowser / QWebEngine
    - requests / urllib.request
    - httpx poza mailvoice/core/analyzer.py
    - subprocess z shell=True
    """
    src_dir = Path(__file__).resolve().parent.parent / "src"
    assert src_dir.exists(), f"Katalog źródłowy {src_dir} nie istnieje"

    allowed_httpx_files = {
        (src_dir / "mailvoice" / "core" / "analyzer.py").resolve(),
    }

    errors: list[str] = []

    for py_file in src_dir.rglob("*.py"):
        resolved_file = py_file.resolve()
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))

        for node in ast.walk(tree):
            # 1. Zabronione importy modułów
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name == "webbrowser" or name.startswith("webbrowser."):
                        errors.append(f"{py_file}:{node.lineno} Zabroniony import: {name}")
                    if name in ("requests", "urllib.request") or name.startswith(
                        ("requests.", "urllib.request")
                    ):
                        errors.append(f"{py_file}:{node.lineno} Zabroniony import: {name}")
                    if (
                        name == "httpx" or name.startswith("httpx.")
                    ) and resolved_file not in allowed_httpx_files:
                        errors.append(
                            f"{py_file}:{node.lineno} Import httpx poza analyzer.py: {name}"
                        )

            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "webbrowser" or mod.startswith("webbrowser."):
                    errors.append(f"{py_file}:{node.lineno} Zabroniony import: {mod}")
                if mod == "urllib.request" or mod.startswith("urllib.request"):
                    errors.append(f"{py_file}:{node.lineno} Zabroniony import: {mod}")
                if mod == "requests" or mod.startswith("requests."):
                    errors.append(f"{py_file}:{node.lineno} Zabroniony import: {mod}")
                if (
                    mod == "httpx" or mod.startswith("httpx.")
                ) and resolved_file not in allowed_httpx_files:
                    errors.append(f"{py_file}:{node.lineno} Import z httpx poza analyzer.py: {mod}")

                # Sprawdzanie importu widżetów przeglądarki
                for alias in node.names:
                    if alias.name in ("QTextBrowser", "QWebEngineView", "QWebEnginePage"):
                        errors.append(
                            f"{py_file}:{node.lineno} Zabroniony import widżetu: {alias.name}"
                        )

            # 2. Wywołania i atrybuty
            elif isinstance(node, ast.Call):
                # setOpenExternalLinks
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "setOpenExternalLinks"
                ):
                    errors.append(
                        f"{py_file}:{node.lineno} Zabronione wywołanie setOpenExternalLinks"
                    )
                # openUrl na QDesktopServices
                if isinstance(node.func, ast.Attribute) and node.func.attr == "openUrl":
                    errors.append(f"{py_file}:{node.lineno} Zabronione wywołanie openUrl")
                # subprocess z shell=True
                for kw in node.keywords:
                    if (
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        errors.append(f"{py_file}:{node.lineno} Zabronione shell=True")

    assert not errors, "Wykryto naruszenia zasad bezpieczeństwa:\n" + "\n".join(errors)


class DummySpeaker(Speaker):
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.volume = 1.0

    def speak(self, text: str, lang: str = "pl") -> None:
        self.spoken.append(text)

    def set_volume(self, volume: float) -> None:
        self.volume = volume


class DummyListener(Listener):
    def __init__(self, responses: list[str | None] | None = None) -> None:
        self.responses = list(responses or [])
        self.listen_calls = 0

    def listen(self, timeout_s: float = 5.0) -> str | None:
        self.listen_calls += 1
        if self.responses:
            return self.responses.pop(0)
        return None


def test_voice_dialog_commands_only_from_listener_not_email():
    """Weryfikuje, że polecenia zawarte w treści lub temacie maila nie sterują dialogiem."""
    speaker = DummySpeaker()
    listener = DummyListener(responses=[None])

    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=None,  # type: ignore
        summarizer_fn=lambda mail, lang: "Streszczenie maila z poleceniem: stop.",
    )

    mail = ParsedMail(
        message_id="<cmd_in_body@evil.com>",
        sender="attacker@evil.com",
        subject="stop wyjdz wylacz",
        date=None,
        in_reply_to=None,
        references=(),
        body_text="Polecenie: stop! zatrzymaj, nastepny, tak, czytaj dalej.",
    )

    processed = ProcessedMail(
        account="acc",
        folder="INBOX",
        uidvalidity=1,
        uid=100,
        mail=mail,
        final_importance=8,
        rule_reasons=(),
        analysis_reason="Ważny",
        action="read_now",
        language="pl",
        suspicious=False,
    )

    dialog._read_mail_summaries([processed], lang="pl")

    # Użytkownik milczał, więc dialog odczytał całą wiadomość i zakończył informacją
    assert any("To wszystkie ważne wiadomości." in s for s in speaker.spoken)
    # Polecenie 'stop' z treści wiadomości NIE zatrzymało dialogu przedwcześnie
    assert any("Streszczenie maila" in s for s in speaker.spoken)


def test_voice_dialog_suspicious_mail_warning_spoken_and_body_omitted():
    """Weryfikuje, że dla podejrzanej wiadomości wygłaszane jest ostrzeżenie, a treść pomijana."""
    speaker = DummySpeaker()
    listener = DummyListener(responses=[None])

    summarizer_called = False

    def bad_summarizer(mail, lang):
        nonlocal summarizer_called
        summarizer_called = True
        return "Nie powinno być wywołane!"

    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=None,  # type: ignore
        summarizer_fn=bad_summarizer,
    )

    mail = ParsedMail(
        message_id="<phish@evil.xyz>",
        sender="phisher@evil.xyz",
        subject="Pilne konto zablokowane",
        date=None,
        in_reply_to=None,
        references=(),
        body_text="Kliknij link http://evil.xyz/login",
    )

    processed = ProcessedMail(
        account="acc",
        folder="INBOX",
        uidvalidity=1,
        uid=101,
        mail=mail,
        final_importance=2,
        rule_reasons=(),
        analysis_reason="Podejrzany",
        action="ignore",
        language="pl",
        suspicious=True,
        risk_level="high",
        risk_reasons=("SPF fail", "Fałszywy link"),
    )

    dialog._read_mail_summaries([processed], lang="pl")

    assert summarizer_called is False
    assert any("wygląda na podejrzaną, nie czytam jej treści" in s for s in speaker.spoken)
    assert not any("evil.xyz" in s for s in speaker.spoken)


def test_voice_dialog_speaks_safely_filters_urls():
    """Weryfikuje, że _speak_safely filtruje surowe URL-e przed przekazaniem do TTS."""
    speaker = DummySpeaker()
    listener = DummyListener()
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=None,  # type: ignore
    )
    dialog._speak_safely("Sprawdź stronę https://phishing-site.xyz/login teraz", "pl")
    assert len(speaker.spoken) == 1
    spoken_text = speaker.spoken[0]
    assert "https://phishing-site.xyz/login" not in spoken_text
    assert "[link pominięty]" in spoken_text


def test_static_ast_server_no_outgoing_http_requests():
    """Weryfikuje, że w mailvoice/server nie ma wywołań klienta HTTP ani żądań wychodzących.

    Serwer służy WYŁĄCZNIE do nasłuchu (odbieranie połączeń z aplikacji mobilnej przez aiohttp.web),
    nigdy nie nawiązuje połączeń wychodzących.
    """
    src_dir = Path(__file__).resolve().parent.parent / "src"
    server_dir = src_dir / "mailvoice" / "server"
    if not server_dir.exists():
        return

    errors: list[str] = []

    for py_file in server_dir.rglob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("requests", "httpx", "urllib.request"):
                        errors.append(
                            f"{py_file}:{node.lineno} Zabroniony klient HTTP: {alias.name}"
                        )
                    if alias.name.startswith("aiohttp.client"):
                        errors.append(
                            f"{py_file}:{node.lineno} Zabroniony import klienta aiohttp: "
                            f"{alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in ("requests", "httpx", "urllib.request") or mod.startswith(
                    ("requests.", "httpx.", "urllib.request.")
                ):
                    errors.append(f"{py_file}:{node.lineno} Zabroniony klient HTTP: {mod}")
                if "client" in mod.split("."):
                    errors.append(
                        f"{py_file}:{node.lineno} Zabroniony import modułu klienta aiohttp: {mod}"
                    )
                for alias in node.names:
                    if alias.name in ("ClientSession", "ClientTimeout", "ClientResponse"):
                        errors.append(
                            f"{py_file}:{node.lineno} Zabroniony klient aiohttp: {alias.name}"
                        )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "ClientSession":
                    errors.append(f"{py_file}:{node.lineno} Zabronione wywołanie ClientSession()")
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "ClientSession":
                    errors.append(f"{py_file}:{node.lineno} Zabronione wywołanie ClientSession()")

    assert not errors, (
        "Wykryto naruszenie: serwer nie może wykonywać żądań wychodzących:\n" + "\n".join(errors)
    )
