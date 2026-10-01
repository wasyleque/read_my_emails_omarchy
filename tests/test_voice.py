"""Testy modułów głosowych (tts, stt, beeper, dialog)."""

from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mailvoice.core.config import AppConfig
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import ProcessedMail
from mailvoice.core.scheduler import NotificationAction
from mailvoice.core.secrets import EncryptedFileStore
from mailvoice.core.service import BacklogQuestion, BeepReminder, MailService, NewImportant
from mailvoice.core.store import Store
from mailvoice.voice.beeper import FakeBeeper
from mailvoice.voice.dialog import VoiceCommand, VoiceDialog, classify_command, normalize_speech
from mailvoice.voice.stt import FakeListener
from mailvoice.voice.tts import FakeSpeaker, VoiceUnavailable


def _create_sample_mail(
    uid: int = 1, sender: str = "szef@firma.pl", subject: str = "Spotkanie"
) -> ProcessedMail:
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content("Treść wiadomości...")
    parsed = ParsedMail(
        message_id=f"<m{uid}@test>",
        sender=sender,
        subject=subject,
        date=datetime.now(timezone.utc),
        in_reply_to=None,
        references=(),
        body_text="Treść wiadomości...",
    )
    return ProcessedMail(
        account="acc1",
        folder="INBOX",
        uidvalidity=1,
        uid=uid,
        mail=parsed,
        final_importance=8,
        rule_reasons=(),
        analysis_reason="Ważne",
        action="read_now",
        language="pl",
    )


@pytest.fixture
def dummy_service(tmp_path: Path):
    store = Store(":memory:")
    sec = EncryptedFileStore(tmp_path / "sec.json", "pass")
    cfg = AppConfig()
    ollama = MagicMock()
    svc = MailService(config=cfg, store=store, secret_store=sec, ollama_client=ollama)
    yield svc
    store.close()


def test_normalize_speech_and_classify():
    assert normalize_speech("Później!") == "pozniej"
    assert normalize_speech("GŁOŚNIEJ, proszę.") == "glosniej prosze"

    assert classify_command("Tak!") == VoiceCommand.YES
    assert classify_command("Yes, sure") == VoiceCommand.YES
    assert classify_command("Później") == VoiceCommand.NO
    assert classify_command("Not now") == VoiceCommand.NO
    assert classify_command("Następny") == VoiceCommand.NEXT
    assert classify_command("Powtórz jeszcze raz") == VoiceCommand.REPEAT
    assert classify_command("Pomiń") == VoiceCommand.SKIP
    assert classify_command("Zatrzymaj to") == VoiceCommand.STOP
    assert classify_command("Głośniej!") == VoiceCommand.LOUDER
    assert classify_command("Ciszej") == VoiceCommand.QUIETER
    assert classify_command("losowy bełkot 123") == VoiceCommand.UNKNOWN


def test_dialog_new_important_flow_yes(dummy_service):
    speaker = FakeSpeaker()
    # 1. Odpowiedź na pytanie: "Tak"
    # 2. Odpowiedź po pierwszym mailu: "Następny"
    listener = FakeListener(["Tak", "Następny"])
    beeper = FakeBeeper()

    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
        beeper=beeper,
        summarizer_fn=lambda mail, lang: "Krótkie streszczenie maila.",
    )

    mail1 = _create_sample_mail(1, "a@firma.pl", "Mail 1")
    mail2 = _create_sample_mail(2, "b@firma.pl", "Mail 2")
    event = NewImportant(items=[mail1, mail2], action=NotificationAction.ASK)

    dialog.handle_event(event)

    # Sprawdzenie wypowiedzianych kwestii
    spoken_texts = [text for text, _ in speaker.spoken]
    assert any("Masz 2 ważnych maili" in t for t in spoken_texts)
    assert any("Mail 1" in t for t in spoken_texts)
    assert any("Mail 2" in t for t in spoken_texts)
    assert any("To wszystkie ważne wiadomości" in t for t in spoken_texts)


def test_dialog_new_important_flow_no(dummy_service):
    speaker = FakeSpeaker()
    listener = FakeListener(["Nie, później"])
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
    )

    mail = _create_sample_mail(1)
    event = NewImportant(items=[mail], action=NotificationAction.ASK)
    dialog.handle_event(event)

    spoken_texts = [text for text, _ in speaker.spoken]
    assert any("Dobrze, przypomnę później" in t for t in spoken_texts)
    assert not any("Treść wiadomości" in t for t in spoken_texts)


def test_dialog_timeout_retry_then_decline(dummy_service):
    speaker = FakeSpeaker()
    # Pierwszy listen: None (cisza) -> ponowienie -> None (cisza)
    listener = FakeListener([None, None])
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
    )

    mail = _create_sample_mail(1)
    dialog.handle_event(NewImportant(items=[mail], action=NotificationAction.ASK))

    spoken_texts = [text for text, _ in speaker.spoken]
    assert any("Przepraszam, nie usłyszałem" in t for t in spoken_texts)
    assert any("Dobrze, przypomnę później" in t for t in spoken_texts)


def test_dialog_commands_repeat_and_stop(dummy_service):
    speaker = FakeSpeaker()
    # Pytanie: "Tak" -> Po mailu 1: "Powtórz" -> Po powtórzeniu: "Stop"
    listener = FakeListener(["Tak", "Powtórz", "Stop"])
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
        summarizer_fn=lambda mail, lang: "Streszczenie.",
    )

    mail1 = _create_sample_mail(1, subject="Temat 1")
    mail2 = _create_sample_mail(2, subject="Temat 2")
    dialog.handle_event(NewImportant(items=[mail1, mail2], action=NotificationAction.ASK))

    spoken_texts = [text for text, _ in speaker.spoken]
    # Temat 1 powinien być przeczytany dwukrotnie (pierwszy raz + powtórzenie)
    mail1_reads = [t for t in spoken_texts if "Temat 1" in t]
    assert len(mail1_reads) == 2
    # Temat 2 nie powinien być odczytany z powodu Stop
    assert not any("Temat 2" in t for t in spoken_texts)
    assert any("Zatrzymano" in t for t in spoken_texts)


def test_dialog_backlog_question(dummy_service):
    speaker = FakeSpeaker()
    listener = FakeListener(["Tak"])
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
        summarizer_fn=lambda mail, lang: "Streszczenie zaległości.",
    )

    mail = _create_sample_mail(10, subject="Zaległy mail")
    dialog.handle_event(BacklogQuestion(items=[mail], count=1))

    spoken_texts = [text for text, _ in speaker.spoken]
    assert any("Masz 1 starszych nieprzeczytanych" in t for t in spoken_texts)
    assert any("Zaległy mail" in t for t in spoken_texts)


def test_dialog_fido2_presence_hook(dummy_service):
    speaker = FakeSpeaker()
    listener = FakeListener(["Tak"])
    # Hak FIDO2 odmawia obecności
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
        confirm_presence=lambda: False,
    )

    mail = _create_sample_mail(1)
    dialog.handle_event(NewImportant(items=[mail], action=NotificationAction.ASK))

    spoken_texts = [text for text, _ in speaker.spoken]
    assert any("Wymagane potwierdzenie kluczem bezpieczeństwa" in t for t in spoken_texts)
    assert not any("Treść wiadomości" in t for t in spoken_texts)


def test_dialog_handles_voice_unavailable(dummy_service):
    class BrokenSpeaker:
        def speak(self, text, lang="pl"):
            raise VoiceUnavailable("Brak silnika TTS")
        def stop(self):
            pass
        def set_volume(self, v):
            pass

    class BrokenListener:
        def listen(self, timeout_s=5.0):
            raise VoiceUnavailable("Brak mikrofonu")

    dialog = VoiceDialog(
        speaker=BrokenSpeaker(),
        listener=BrokenListener(),
        service=dummy_service,
    )
    # Wywołanie nie może rzucić wyjątkiem
    dialog.handle_event(NewImportant(items=[_create_sample_mail(1)], action=NotificationAction.ASK))
    dialog.handle_event(BeepReminder(count=1))
