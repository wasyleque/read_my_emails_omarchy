"""Testy modułów głosowych (tts, stt, beeper, dialog)."""

from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mailvoice.core.aisearch import MailRef, SearchHit
from mailvoice.core.config import AppConfig
from mailvoice.core.contacts import ContactCard
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import ProcessedMail
from mailvoice.core.scheduler import NotificationAction
from mailvoice.core.secrets import EncryptedFileStore
from mailvoice.core.service import (
    BacklogQuestion,
    BeepReminder,
    ContactCardReady,
    DigestReady,
    MailService,
    NewImportant,
    SearchResults,
)
from mailvoice.core.store import Store
from mailvoice.voice.beeper import FakeBeeper
from mailvoice.voice.dialog import (
    VoiceCommand,
    VoiceDialog,
    classify_command,
    normalize_speech,
    parse_contact_query,
    parse_digest_days,
    parse_search_query,
)
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


def test_dialog_digest_command_and_speech(dummy_service):
    from mailvoice.core.digest import Digest, Participant, Topic

    # Test rozpoznawania komend tekstowych/głosowych
    assert classify_command("podsumuj miesiąc") == VoiceCommand.DIGEST
    assert classify_command("podsumuj tydzień") == VoiceCommand.DIGEST
    assert classify_command("summarize last month") == VoiceCommand.DIGEST
    assert parse_digest_days("podsumuj tydzień") == 7
    assert parse_digest_days("podsumuj miesiąc") == 30
    assert parse_digest_days("podsumuj 14 dni") == 14

    speaker = FakeSpeaker()
    # Pierwszy topic -> powtórz, potem następny
    listener = FakeListener(["powtórz", "następny"])
    dialog = VoiceDialog(
        speaker=speaker,
        listener=listener,
        service=dummy_service,
    )

    t1 = Topic(
        title="Sprawa umowy",
        participants=[Participant(address="anna@corp.com", role="from", count=1)],
        who_to_whom=["Anna -> Jan w sprawie umowy"],
        why="Czekamy na podpis.",
        status="oczekuje_na_mnie",
        last_activity=datetime.now(timezone.utc),
        importance=8,
        mail_count=1,
    )
    t2 = Topic(
        title="Biuletyn techniczny",
        participants=[Participant(address="news@it.com", role="from", count=1)],
        who_to_whom=[],
        why="Nowinki technologiczne.",
        status="informacyjne",
        last_activity=datetime.now(timezone.utc),
        importance=3,
        mail_count=1,
    )
    digest = Digest(period="ostatnie 30 dni", topics=[t1, t2])

    dialog.handle_event(DigestReady(digest=digest))

    spoken = [text for text, _ in speaker.spoken]
    # Sprawa umowy powinna być przeczytana dwukrotnie przez "powtórz"
    t1_reads = [s for s in spoken if "Sprawa umowy" in s]
    assert len(t1_reads) == 2
    assert any("czeka na Twoją odpowiedź" in s for s in t1_reads)

    # Biuletyn przeczytany
    assert any("Biuletyn techniczny" in s for s in spoken)
    assert any("To wszystkie tematy z tego okresu" in s for s in spoken)


def test_dialog_contact_queries_and_speech(dummy_service):
    # Parsowanie zapytań
    assert parse_contact_query("kim jest Kowalski") == "kowalski"
    assert parse_contact_query("co z Anną") == "anna"
    assert parse_contact_query("who is John Doe") == "john doe"
    assert parse_contact_query("what about Alice") == "alice"
    assert classify_command("kim jest Kowalski") == VoiceCommand.CONTACT

    speaker = FakeSpeaker()
    listener = FakeListener(["tak"])
    dialog = VoiceDialog(speaker=speaker, listener=listener, service=dummy_service)

    # 1. Nieznany kontakt - dialog informuje i pyta o szukanie AI
    dummy_service.contact_context = MagicMock(return_value=None)
    dummy_service.ai_search = MagicMock(return_value=[])

    handled = dialog.handle_speech_command("kim jest Nieznajomy")
    assert handled is True
    dummy_service.contact_context.assert_called_with("nieznajomy")
    spoken = [text for text, _ in speaker.spoken]
    assert any("Nie znam tego nadawcy" in s for s in spoken)
    # Po "tak" użytkownika, wywołano ai_search
    dummy_service.ai_search.assert_called_with("nieznajomy")

    # 2. Znany kontakt
    card = ContactCard(
        name="Jan Kowalski",
        addresses=("jan@firma.pl",),
        first_seen=datetime.now(timezone.utc),
        last_contact=datetime.now(timezone.utc),
        mail_count=3,
        topics=[],
        open_items=["Zatwierdzenie faktury"],
        last_exchange=[(datetime.now(timezone.utc), "odebrany", "Faktura za remont")],
        relationship_hint="Główny księgowy",
        why_it_matters="Płatności i podatki",
    )
    dummy_service.contact_context = MagicMock(return_value=card)
    speaker.spoken.clear()

    handled = dialog.handle_speech_command("co z Kowalskim")
    assert handled is True
    spoken = [text for text, _ in speaker.spoken]
    assert any("Główny księgowy" in s for s in spoken)
    assert any("Zatwierdzenie faktury" in s for s in spoken)

    # 3. Zdarzenie ContactCardReady
    speaker.spoken.clear()
    dialog.handle_event(ContactCardReady(card=card, address_or_name="jan@firma.pl"))
    assert any("Jan Kowalski" in s for s, _ in speaker.spoken)


def test_dialog_search_queries_and_speech(dummy_service):
    # Parsowanie zapytań
    assert parse_search_query("znajdź mail o fakturze") == "o fakturze"
    assert parse_search_query("szukaj maila od Kowalskiego") == "od kowalskiego"
    assert parse_search_query("find email about server") == "about server"
    assert classify_command("znajdź mail o fakturze") == VoiceCommand.SEARCH

    speaker = FakeSpeaker()
    listener = FakeListener(["powtórz", "następny"])
    dialog = VoiceDialog(speaker=speaker, listener=listener, service=dummy_service)

    hit1 = SearchHit(
        mail_ref=MailRef(
            account="acc1",
            folder="INBOX",
            uidvalidity=1,
            uid=10,
            message_id="<m10@test>",
            subject="Faktura za remont",
            sender="Piotr Kowalski <k@test.pl>",
            date="2026-10-01",
        ),
        score=0.9,
        why_probable="Zgadza się nadawca oraz faktura remontowa.",
        snippet="Załączam rozliczenie prac malarskich.",
        confidence="wysoka",
    )
    hit2 = SearchHit(
        mail_ref=MailRef(
            account="acc1",
            folder="INBOX",
            uidvalidity=1,
            uid=11,
            message_id="<m11@test>",
            subject="Oferta remontowa",
            sender="Anna Nowak <n@test.pl>",
            date="2026-09-20",
        ),
        score=0.7,
        why_probable="Dotyczy prac remontowych.",
        snippet="Cennik usług budowlanych.",
        confidence="średnia",
    )

    dummy_service.ai_search = MagicMock(return_value=[hit1, hit2])

    handled = dialog.handle_speech_command("znajdź mail o fakturze")
    assert handled is True
    dummy_service.ai_search.assert_called_with("o fakturze")

    spoken = [text for text, _ in speaker.spoken]
    # Hit 1 powinien być przeczytany 2 razy przez "powtórz"
    hit1_reads = [s for s in spoken if "Piotr Kowalski" in s]
    assert len(hit1_reads) == 2
    assert any("Faktura za remont" in s for s in spoken)
    assert any("Anna Nowak" in s for s in spoken)
    assert any("To wszystkie znalezione wiadomości" in s for s in spoken)

    # Test zdarzenia SearchResults
    speaker.spoken.clear()
    dialog.handle_event(SearchResults(query="o fakturze", hits=[hit1]))
    assert any("Piotr Kowalski" in s for s, _ in speaker.spoken)

