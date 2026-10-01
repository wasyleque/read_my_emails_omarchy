"""Moduł generowania streszczeń wiadomości e-mail przy użyciu modelu Ollama."""

import re
from typing import Any

from mailvoice.core.analyzer import OllamaClient, pick_model
from mailvoice.core.config import AppConfig, OllamaConfig
from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.textutil import truncate_for_llm

ABBREVIATIONS = {
    "dr",
    "prof",
    "mgr",
    "inż",
    "inz",
    "hab",
    "mr",
    "mrs",
    "ms",
    "np",
    "itd",
    "itp",
    "tzw",
    "tzn",
    "al",
    "ul",
    "pl",
    "art",
    "str",
    "par",
    "ust",
    "e.g",
    "i.e",
    "etc",
    "vs",
    "ok",
    "godz",
    "m.in",
}


def split_sentences(text: str) -> list[str]:
    """Dzieli tekst na zdania, ignorując kropki w typowych skrótach (np. Dr., godz.)."""
    text = text.strip()
    if not text:
        return []

    pattern = re.compile(r"([.!?]+)(?:\s+|$)")
    sentences: list[str] = []
    start = 0

    for match in pattern.finditer(text):
        end = match.end()
        punct_start = match.start()

        # Sprawdzamy słowo tuż przed znakiem interpunkcyjnym
        prefix = text[start:punct_start]
        words = prefix.split()
        if words:
            last_word = words[-1].lower().rstrip(".!?")
            if last_word in ABBREVIATIONS:
                continue
            # Inicjał (np. "J.")
            if len(last_word) == 1 and last_word.isalpha():
                continue

        sent = text[start:end].strip()
        if sent:
            sentences.append(sent)
        start = end

    if start < len(text):
        remaining = text[start:].strip()
        if remaining:
            if sentences:
                sentences[-1] = sentences[-1] + " " + remaining
            else:
                sentences.append(remaining)

    return sentences


def limit_sentences(text: str, max_sentences: int = 4) -> str:
    """Ogranicza tekst do maksymalnie `max_sentences` zdań."""
    sentences = split_sentences(text)
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    return " ".join(sentences[:max_sentences])


def build_summary_messages(mail: ParsedMail, language: str) -> list[dict[str, str]]:
    """Buduje listę komunikatów dla modelu LLM do wygenerowania streszczenia."""
    body_text = truncate_for_llm(mail.body_text, 3000)

    if language == "en":
        system_content = (
            "You are a helpful email assistant. "
            "Write a concise summary of the following email in at most 3-4 sentences in English. "
            "Focus on the general thread and key action items or decisions. "
            "Do NOT read the whole text and do NOT add intro phrases like 'Here is the summary:'."
        )
        user_content = f"From: {mail.sender}\nSubject: {mail.subject}\nBody:\n{body_text}"
    else:
        system_content = (
            "Jesteś asystentem pocztowym. "
            "Napisz zwięzłe streszczenie poniższego maila w maksymalnie 3-4 zdaniach "
            "w języku polskim. "
            "Uogólnij wątek oraz kluczowe informacje lub wymagane działania. "
            "Nie czytaj całości ani nie dodawaj zwrotów wstępnych typu 'Oto streszczenie:'."
        )
        user_content = f"Od: {mail.sender}\nTemat: {mail.subject}\nTreść:\n{body_text}"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def summarize(
    client: OllamaClient,
    cfg: AppConfig | OllamaConfig | Any,
    mail: ParsedMail,
    language: str = "pl",
) -> str:
    """Generuje streszczenie maila w maksymalnie 4 zdaniach.

    Obsługuje pustą treść bez wywoływania modelu LLM.
    """
    clean_body = mail.body_text.strip()
    if not clean_body:
        if language == "en":
            return (
                f"No message body. Subject: {mail.subject}."
                if mail.subject
                else "Empty message."
            )
        return (
            f"Wiadomość bez treści. Temat: {mail.subject}."
            if mail.subject
            else "Wiadomość bez treści."
        )

    ollama_cfg: OllamaConfig = cfg.ollama if hasattr(cfg, "ollama") else cfg
    target_lang = "en" if language == "en" else "pl"
    model = pick_model(target_lang, ollama_cfg)
    messages = build_summary_messages(mail, target_lang)

    raw_summary = client.chat_text(messages, model)
    return limit_sentences(raw_summary, max_sentences=4)
