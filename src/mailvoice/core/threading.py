"""Moduł łączenia wiadomości w wątki (threading)."""

import re

from mailvoice.core.mailparse import ParsedMail

_PREFIX_RE = re.compile(
    r"^(\s*(re|odp|fwd|fw|aw|sv|wg)(\[\d+\])?:\s*)+",
    re.IGNORECASE,
)


def clean_subject(subject: str) -> str:
    """Usuwa prefiksy odpowiedzi i przekazań (Re:, Odp:, Fwd: itp.) oraz normalizuje spacje."""
    if not subject:
        return ""
    cleaned = subject
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _PREFIX_RE.sub("", cleaned).strip()
    return " ".join(cleaned.split())


def is_reply_or_forward_subject(subject: str) -> bool:
    """Sprawdza, czy temat zawiera prefiks wskazujący na odpowiedź lub przekazanie."""
    if not subject:
        return False
    return bool(_PREFIX_RE.match(subject.strip()))


def thread_key(mail: ParsedMail) -> str:
    """Wyznacza klucz wątku dla wiadomości e-mail.

    1. Jeśli obecne są nagłówki References: korzeniem jest pierwszy Message-ID z References.
    2. Jeśli brak References, ale obecny jest In-Reply-To: używa In-Reply-To.
    3. W przypadku braku nagłówków powiązań:
       - Jeśli wiadomość nie ma prefiksu Re/Odp i ma własny Message-ID: kluczem jest jej Message-ID
         (staje się korzeniem dla przyszłych odpowiedzi).
       - Awaryjnie: znormalizowany temat + zbiór uczestników (kto pisał i do kogo).
    """
    # 1. References -> korzeń wątku
    if mail.references:
        for ref in mail.references:
            cleaned_ref = ref.strip()
            if cleaned_ref:
                return cleaned_ref

    # 2. In-Reply-To
    if mail.in_reply_to and mail.in_reply_to.strip():
        return mail.in_reply_to.strip()

    norm_subj = clean_subject(mail.subject).lower()

    # Jeśli wiadomość jest inicjująca (brak prefiksu Re/Odp) i posiada Message-ID
    if mail.message_id and not is_reply_or_forward_subject(mail.subject):
        return mail.message_id.strip()

    # 3. Awaryjnie po temacie i uczestnikach
    participants = set()
    if mail.sender:
        participants.add(mail.sender.strip().lower())
    for addr in mail.to:
        if addr:
            participants.add(addr.strip().lower())
    for addr in mail.cc:
        if addr:
            participants.add(addr.strip().lower())

    parts_str = ",".join(sorted(participants))
    if norm_subj:
        if parts_str:
            return f"subj:{norm_subj}|parts:{parts_str}"
        return f"subj:{norm_subj}"

    if mail.message_id:
        return mail.message_id.strip()

    return f"parts:{parts_str}" if parts_str else "orphan"
