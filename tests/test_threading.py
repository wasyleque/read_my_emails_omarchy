"""Testy modułu łączenia wiadomości w wątki (core/threading.py)."""

from datetime import datetime, timezone

from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.threading import (
    clean_subject,
    is_reply_or_forward_subject,
    thread_key,
)


def _make_mail(
    subject: str = "Projekt",
    sender: str = "anna@example.com",
    to: tuple[str, ...] = ("jan@example.com",),
    cc: tuple[str, ...] = (),
    message_id: str | None = "<msg1@example.com>",
    in_reply_to: str | None = None,
    references: tuple[str, ...] = (),
) -> ParsedMail:
    return ParsedMail(
        message_id=message_id,
        sender=sender,
        subject=subject,
        date=datetime.now(timezone.utc),
        in_reply_to=in_reply_to,
        references=references,
        body_text="Cześć",
        to=to,
        cc=cc,
    )


def test_clean_subject_prefixes():
    assert clean_subject("Re: Ważny temat") == "Ważny temat"
    assert clean_subject("Odp: Ważny temat") == "Ważny temat"
    assert clean_subject("Fwd: FW: Odp[2]: Re: Temat rozmowy") == "Temat rozmowy"
    assert clean_subject("AW: SV: WG: Temat") == "Temat"
    assert clean_subject("  Re:   Wielokrotne   spacje   ") == "Wielokrotne spacje"
    assert clean_subject("") == ""


def test_is_reply_or_forward_subject():
    assert is_reply_or_forward_subject("Re: Spotkanie") is True
    assert is_reply_or_forward_subject("Odp: Raport") is True
    assert is_reply_or_forward_subject("Fwd: Prezentacja") is True
    assert is_reply_or_forward_subject("Odp[3]: Kolejna odpowiedź") is True
    assert is_reply_or_forward_subject("Nowy temat bez odpowiedzi") is False
    assert is_reply_or_forward_subject("") is False


def test_chain_of_replies_references():
    m1 = _make_mail(
        subject="Oferta współpracy",
        message_id="<root@example.com>",
        references=(),
        in_reply_to=None,
    )
    m2 = _make_mail(
        subject="Re: Oferta współpracy",
        message_id="<reply1@example.com>",
        references=("<root@example.com>",),
        in_reply_to="<root@example.com>",
    )
    m3 = _make_mail(
        subject="Odp: Re: Oferta współpracy",
        message_id="<reply2@example.com>",
        references=("<root@example.com>", "<reply1@example.com>"),
        in_reply_to="<reply1@example.com>",
    )

    k1 = thread_key(m1)
    k2 = thread_key(m2)
    k3 = thread_key(m3)

    assert k1 == "<root@example.com>"
    assert k2 == "<root@example.com>"
    assert k3 == "<root@example.com>"


def test_chain_of_replies_in_reply_to_only():
    m1 = _make_mail(
        subject="Pytanie",
        message_id="<root-q@example.com>",
        in_reply_to=None,
    )
    m2 = _make_mail(
        subject="Odp: Pytanie",
        message_id="<reply-q@example.com>",
        in_reply_to="<root-q@example.com>",
        references=(),
    )

    assert thread_key(m1) == "<root-q@example.com>"
    assert thread_key(m2) == "<root-q@example.com>"


def test_same_subject_different_threads_no_headers():
    # Brak References/In-Reply-To, prefiks Odp: oznacza, że to odpowiedź, ale nie ma nagłówków
    # Dwie różne grupy uczestników z tym samym tematem "Status"
    m_thread_a = _make_mail(
        subject="Odp: Status",
        sender="anna@corp.com",
        to=("jan@corp.com",),
        message_id="<a1@corp.com>",
    )
    m_thread_b = _make_mail(
        subject="Odp: Status",
        sender="karol@other.com",
        to=("eliza@other.com",),
        message_id="<b1@other.com>",
    )

    key_a = thread_key(m_thread_a)
    key_b = thread_key(m_thread_b)

    assert key_a != key_b
    assert "subj:status" in key_a
    assert "anna@corp.com" in key_a and "jan@corp.com" in key_a
    assert "subj:status" in key_b
    assert "karol@other.com" in key_b and "eliza@other.com" in key_b


def test_same_subject_same_participants_no_headers():
    m1 = _make_mail(
        subject="Odp: Raport kwartalny",
        sender="anna@corp.com",
        to=("jan@corp.com",),
        message_id=None,
    )
    m2 = _make_mail(
        subject="Re: Raport kwartalny",
        sender="jan@corp.com",
        to=("anna@corp.com",),
        message_id=None,
    )

    assert thread_key(m1) == thread_key(m2)


def test_no_headers_root_email():
    # Inicjujący mail bez prefiksów odpowiedzi ma swój Message-ID jako thread_key
    m = _make_mail(
        subject="Nowy temat",
        message_id="<init-123@example.com>",
        in_reply_to=None,
        references=(),
    )
    assert thread_key(m) == "<init-123@example.com>"


def test_no_headers_no_id_no_subject():
    m = _make_mail(
        subject="",
        sender="sender@example.com",
        to=(),
        message_id=None,
    )
    assert thread_key(m) == "parts:sender@example.com"
