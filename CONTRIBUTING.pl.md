# Jak współtworzyć MailVoice

MailVoice (GPL-3.0-or-later) pobiera pocztę z kilku skrzynek IMAP **tylko do odczytu**, lokalny model AI (Ollama)
ocenia, co jest ważne, a program informuje głosem po polsku lub angielsku.
[English version](CONTRIBUTING.md)

## Jak zacząć
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,voice]"
ruff check . && QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m mailvoice
```
Na Omarchy/Arch zobacz sekcję *Omarchy* w [README](README.pl.md) (Python 3.12 przez `mise`, `pacman`, nie `apt`).
Dobre miejsca na start: zgłoszenia z etykietą **good first issue**, testy z innymi dostawcami poczty (nazwy folderów,
kodowania, `UIDVALIDITY`) oraz **testy na Windowsie** (audio, mikrofon, FIDO2).

## Struktura kodu
- `src/mailvoice/core/` — logika **bez zależności od Qt** (w pełni testowalna)
- `src/mailvoice/voice/` — wejście i wyjście głosowe za interfejsami `Protocol` (dają się podmieniać w testach)
- `src/mailvoice/ui/` — tylko PySide6, **bez logiki biznesowej**
- `tests/` — pytest

## Zasady kodu
- Każda funkcja w `core/` ma test; poprawka błędu ma test regresji.
- Przed PR muszą przejść `ruff check .` oraz `QT_QPA_PLATFORM=offscreen python -m pytest -q`.
- Identyfikatory po angielsku; komentarze po polsku lub angielsku.
- Żadnych kolorów wpisanych na sztywno w UI — używaj `ui/theme.py`. Teksty interfejsu przez `tr()` w `ui/i18n.py`
  w **obu** językach PL i EN.

## Bezpieczeństwo i prywatność
Przeczytaj [SECURITY.md](SECURITY.pl.md), zanim zmienisz obsługę poczty. Zasady nienaruszalne: nie otwieramy linków z
maili, nie pobieramy załączników, nie wykonujemy instrukcji z treści wiadomości, skrzynka tylko do odczytu, hasła
tylko w sejfie.
**Nigdy nie wklejaj do issues ani PR prawdziwych maili, haseł, tokenów ani prywatnych adresów.** Luki zgłaszaj
prywatnie przez *Security → Report a vulnerability*.

## Zgłaszanie błędów i Pull Requesty
Korzystaj z szablonów zgłoszeń; podaj kroki do odtworzenia, środowisko i ślad błędu z
`~/.local/state/mailvoice/log/mailvoice.log` (bez adresów). PR: opisz co i dlaczego, trzymaj zmiany w ryzach i
upewnij się, że powyższe sprawdzenia przechodzą.
