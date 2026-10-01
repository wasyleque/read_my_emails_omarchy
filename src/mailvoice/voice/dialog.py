"""Moduł maszyny stanów dialogu głosowego (VoiceDialog).

Odpowiada za interakcję głosową z użytkownikiem (pytanie o czas, czytanie streszczeń,
obsługę komend: tak/nie/następny/powtórz/pomiń/stop/głośniej/wycisz).
"""

import unicodedata
from enum import Enum
from typing import Callable, Sequence

from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import PendingBacklog, ProcessedMail
from mailvoice.core.service import (
    AskReminder,
    BacklogQuestion,
    BeepReminder,
    Event,
    MailService,
    NewImportant,
)
from mailvoice.core.summarizer import summarize as core_summarize
from mailvoice.voice.beeper import Beeper, FakeBeeper
from mailvoice.voice.stt import Listener
from mailvoice.voice.tts import Speaker, VoiceUnavailable


class VoiceCommand(str, Enum):
    YES = "yes"
    NO = "no"
    NEXT = "next"
    REPEAT = "repeat"
    SKIP = "skip"
    STOP = "stop"
    LOUDER = "louder"
    QUIETER = "quieter"
    UNKNOWN = "unknown"


def normalize_speech(text: str | None) -> str:
    """Usuwa znaki diakrytyczne, interpunkcję i zamienia na małe litery."""
    if not text:
        return ""
    text = text.replace("ł", "l").replace("Ł", "L")
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in normalized if not unicodedata.combining(c))
    clean = "".join(c for c in stripped if c.isalnum() or c.isspace())
    return " ".join(clean.lower().split())


def classify_command(text: str | None) -> VoiceCommand:
    """Rozpoznaje intencję wypowiedzi użytkownika w języku polskim lub angielskim."""
    norm = normalize_speech(text)
    if not norm:
        return VoiceCommand.UNKNOWN

    words = set(norm.split())

    # Komendy zatrzymania
    stop_words = {"stop", "koniec", "wyjdz", "wylacz", "zatrzymaj", "exit", "quit", "halt"}
    if words & stop_words:
        return VoiceCommand.STOP

    # Komendy głośności
    if any(w in norm for w in ("glosniej", "louder", "podglosnij")):
        return VoiceCommand.LOUDER
    if any(w in norm for w in ("ciszej", "quieter", "scisz", "wycisz", "mute")):
        return VoiceCommand.QUIETER

    # Komendy powtórzenia i pominięcia
    if any(w in norm for w in ("powtorz", "repeat", "jeszcze raz", "again")):
        return VoiceCommand.REPEAT
    if any(w in norm for w in ("pomin", "skip")):
        return VoiceCommand.SKIP

    # Komendy przejścia dalej
    if any(w in norm for w in ("nastepny", "next", "dalej", "kolejny")):
        return VoiceCommand.NEXT

    # Potwierdzenie (Tak)
    yes_words = {
        "tak", "yes", "chce", "slucham", "jasne", "pewnie", "dawaj", "sure", "ok", "dobrze"
    }
    if words & yes_words:
        return VoiceCommand.YES

    # Odrzucenie / Odroczenie (Nie)
    no_phrases = ("nie teraz", "not now")
    no_words = {"nie", "no", "pozniej", "later", "odloz", "not"}
    if any(phrase in norm for phrase in no_phrases) or (words & no_words):
        return VoiceCommand.NO

    return VoiceCommand.UNKNOWN


class VoiceDialog:
    """Maszyna stanów dialogu głosowego obsługująca powiadomienia i komendy."""

    def __init__(
        self,
        speaker: Speaker,
        listener: Listener,
        service: MailService,
        beeper: Beeper | None = None,
        confirm_presence: Callable[[], bool] | None = None,
        summarizer_fn: Callable[[ParsedMail, str], str] | None = None,
        default_lang: str = "pl",
    ) -> None:
        self.speaker = speaker
        self.listener = listener
        self.service = service
        self.beeper = beeper or FakeBeeper()
        self.confirm_presence = confirm_presence or (lambda: True)
        self.summarizer_fn = summarizer_fn or self._default_summarize
        self.default_lang = default_lang

    def _default_summarize(self, mail: ParsedMail, lang: str) -> str:
        try:
            return core_summarize(
                self.service.ollama_client,
                self.service.config,
                mail,
                language=lang,
            )
        except Exception:
            # Fallback jeśli Ollama nie odpowiada
            if lang == "en":
                return f"Subject: {mail.subject}. Content preview: {mail.body_text[:100]}"
            return f"Temat: {mail.subject}. Początek treści: {mail.body_text[:100]}"

    def _speak_safely(self, text: str, lang: str) -> None:
        try:
            self.speaker.speak(text, lang=lang)
        except VoiceUnavailable:
            pass

    def _listen_with_retry(self, lang: str) -> str | None:
        """Nasłuchuje wypowiedzi; w razie ciszy ponawia prośbę jeden raz."""
        try:
            ans = self.listener.listen(timeout_s=5.0)
            if ans is not None and ans.strip():
                return ans

            # Jednokrotne grzeczne ponowienie
            retry_prompt = (
                "Przepraszam, nie usłyszałem. Czy chcesz posłuchać teraz?"
                if lang == "pl"
                else "Sorry, I didn't hear you. Would you like to listen now?"
            )
            self._speak_safely(retry_prompt, lang)
            return self.listener.listen(timeout_s=5.0)
        except VoiceUnavailable:
            return None

    def handle_event(self, event: Event) -> None:
        """Główny punkt wejścia zdarzeń z MailService do dialogu głosowego."""
        lang = self.default_lang

        if isinstance(event, BeepReminder):
            self.beeper.beep()
            return

        if isinstance(event, AskReminder):
            self._handle_ask_flow(event.count, lang)
            return

        if isinstance(event, NewImportant):
            if event.action.value == "beep":
                self.beeper.beep()
            else:
                self._handle_new_important_flow(event.items, lang)
            return

        if isinstance(event, BacklogQuestion):
            self._handle_backlog_flow(event.items, event.count, lang)

    def _handle_ask_flow(self, count: int, lang: str) -> None:
        prompt = (
            f"Przypomnienie: masz {count} ważnych maili. Czy masz teraz czas posłuchać?"
            if lang == "pl"
            else f"Reminder: you have {count} important emails. Do you have time to listen now?"
        )
        self._speak_safely(prompt, lang)
        answer = self._listen_with_retry(lang)
        cmd = classify_command(answer)

        if cmd == VoiceCommand.YES:
            self.service.user_confirm()
            if not self.confirm_presence():
                self._speak_safely(
                    "Wymagane potwierdzenie kluczem bezpieczeństwa."
                    if lang == "pl"
                    else "Security key confirmation required.",
                    lang,
                )
                return
            self._speak_safely(
                "Słucham. Przechodzę do wiadomości."
                if lang == "pl"
                else "Great. Reading messages.",
                lang,
            )
        else:
            self.service.user_decline()
            msg = (
                "Dobrze, przypomnę później."
                if lang == "pl"
                else "Alright, I will remind you later."
            )
            self._speak_safely(msg, lang)

    def _handle_new_important_flow(self, items: list[ProcessedMail], lang: str) -> None:
        count = len(items)
        prompt = (
            f"Masz {count} ważnych maili. Czy masz teraz czas posłuchać?"
            if lang == "pl"
            else f"You have {count} important emails. Do you have time to listen now?"
        )
        self._speak_safely(prompt, lang)
        answer = self._listen_with_retry(lang)
        cmd = classify_command(answer)

        if cmd == VoiceCommand.YES:
            self.service.user_confirm()
            if not self.confirm_presence():
                self._speak_safely(
                    "Wymagane potwierdzenie kluczem bezpieczeństwa."
                    if lang == "pl"
                    else "Security key confirmation required.",
                    lang,
                )
                return
            self._read_mail_summaries(items, lang)
        else:
            self.service.user_decline()
            msg = (
                "Dobrze, przypomnę później."
                if lang == "pl"
                else "Alright, I will remind you later."
            )
            self._speak_safely(msg, lang)

    def _handle_backlog_flow(
        self, items: Sequence[ProcessedMail | PendingBacklog], count: int, lang: str
    ) -> None:
        if lang == "pl":
            prompt = (
                f"Masz {count} starszych nieprzeczytanych ważnych maili. "
                "Czy chcesz usłyszeć streszczenia?"
            )
        else:
            prompt = (
                f"You have {count} older unread important emails. "
                "Would you like to hear summaries?"
            )
        self._speak_safely(prompt, lang)
        answer = self._listen_with_retry(lang)
        cmd = classify_command(answer)

        if cmd == VoiceCommand.YES:
            self.service.resolve_backlog(accepted=True, items=items)
            if not self.confirm_presence():
                self._speak_safely(
                    "Wymagane potwierdzenie kluczem bezpieczeństwa."
                    if lang == "pl"
                    else "Security key confirmation required.",
                    lang,
                )
                return
            processed_items = [it for it in items if isinstance(it, ProcessedMail)]
            if processed_items:
                self._read_mail_summaries(processed_items, lang)
            else:
                self._speak_safely(
                    "Zaległości zostały zatwierdzone."
                    if lang == "pl"
                    else "Backlog confirmed.",
                    lang,
                )
        else:
            self.service.resolve_backlog(accepted=False, items=items)
            self._speak_safely(
                "Dobrze, oznaczyłem zaległości jako pominięte."
                if lang == "pl"
                else "Alright, marked backlog as skipped.",
                lang,
            )

    def _read_mail_summaries(self, items: list[ProcessedMail], lang: str) -> None:
        idx = 0
        total = len(items)

        while idx < total:
            item = items[idx]
            mail_lang = item.language if item.language in ("pl", "en") else lang
            summary = self.summarizer_fn(item.mail, mail_lang)

            if mail_lang == "en":
                header = (
                    f"Message {idx + 1} of {total}. "
                    f"From {item.mail.sender}. Subject: {item.mail.subject}. "
                )
            else:
                header = (
                    f"Wiadomość {idx + 1} z {total}. "
                    f"Od {item.mail.sender}. Temat: {item.mail.subject}. "
                )

            self._speak_safely(header + summary, mail_lang)

            if idx + 1 < total:
                continue_prompt = "Czytać dalej?" if mail_lang == "pl" else "Continue?"
                self._speak_safely(continue_prompt, mail_lang)
                cmd_text = self.listener.listen(timeout_s=5.0)
                cmd = classify_command(cmd_text)

                if cmd == VoiceCommand.REPEAT:
                    continue  # Powtarzamy ten sam mail (bez zwiększania idx)

                if cmd in (VoiceCommand.STOP, VoiceCommand.NO):
                    self._speak_safely(
                        "Zatrzymano." if mail_lang == "pl" else "Stopped.", mail_lang
                    )
                    return

                if cmd == VoiceCommand.LOUDER:
                    current_vol = getattr(self.speaker, "volume", 1.0)
                    self.speaker.set_volume(min(2.0, current_vol + 0.2))
                    self._speak_safely("Głośniej." if mail_lang == "pl" else "Louder.", mail_lang)
                    idx += 1
                    continue

                if cmd == VoiceCommand.QUIETER:
                    current_vol = getattr(self.speaker, "volume", 1.0)
                    self.speaker.set_volume(max(0.2, current_vol - 0.2))
                    self._speak_safely("Ciszej." if mail_lang == "pl" else "Quieter.", mail_lang)
                    idx += 1
                    continue

                # NEXT, SKIP, YES lub domyślnie
                idx += 1
            else:
                idx += 1

        self._speak_safely(
            "To wszystkie ważne wiadomości."
            if lang == "pl"
            else "That is all important messages.",
            lang,
        )
