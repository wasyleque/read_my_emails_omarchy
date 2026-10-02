"""Gdzie odtwarzać automatyczne powiadomienia głosowe: komputer, telefon czy oba."""

from __future__ import annotations

VOICE_OUTPUT_CHOICES = ("auto", "computer", "phone", "both")


def computer_should_speak(mode: str, phones_online: int) -> bool:
    """Czy komputer ma sam czytać/pikać przy zdarzeniu systemowym (nowy ważny mail, przypomnienie).

    - auto: telefon, gdy jest połączony; inaczej komputer (zalecane — bez dublowania)
    - computer / both: komputer czyta zawsze
    - phone: komputer milczy (powiadomienia trafiają tylko na telefon)
    Odtwarzanie wywołane przez użytkownika na komputerze (np. „Posłuchaj”) nie podlega tej regule.
    """
    if mode in ("computer", "both"):
        return True
    if mode == "phone":
        return False
    return phones_online <= 0
