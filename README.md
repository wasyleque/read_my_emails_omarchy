# MailVoice (read_my_emails_omarchy)

> 🚧 **Projekt roboczy / work in progress.** Rdzeń logiki działa i ma testy, GUI i głos są jeszcze w planach.
> Zgłoszenia błędów i pomysły są mile widziane.

Aplikacja GUI na **Linux (Omarchy) i Windows**, która pobiera pocztę z kilku skrzynek IMAP, a **lokalny model AI
(Ollama)** ocenia, które nowe maile są naprawdę ważne. O ważnych mailach informuje **głosem po polsku lub angielsku**
i streszcza je w 3–4 zdaniach zamiast czytać całość.

*English: a cross-platform (Linux/Windows) desktop app that fetches mail from several IMAP accounts, uses a local
Ollama model to decide which new mails matter, and tells you by voice (Polish/English) with a 3–4 sentence summary.
Nothing is ever sent, deleted or marked as read.*

## Jak to działa

1. Co N minut pobiera **tylko nowe** maile (UID większy niż ostatnio widziany, dedup po `Message-ID`).
2. **Reguły bez LLM:** nadawcy VIP, słowa kluczowe, blokady, odpowiedzi na Twoje wysłane maile.
3. **Model lokalny** ocenia resztę wg Twojego opisu "jak analizować maile" i zwraca ustrukturyzowany JSON
   (ważność 0–10, powód, akcja, język).
4. Powiadomienie: powtarzany sygnał dźwiękowy **albo** pytanie głosowe "masz czas wysłuchać nowych maili?".
5. Zaległe, **nieprzeczytane** starsze maile, które wyglądają na ważne, są zgłaszane osobno: aplikacja pyta, czy
   chcesz usłyszeć ich streszczenia.

**Prywatność i bezpieczeństwo:** dostęp do poczty jest wyłącznie do odczytu (`BODY.PEEK`, flagi się nie zmieniają),
treść maili trafia tylko do Twojego Ollamy, a hasła mają być trzymane w systemowym keyringu (w planach opcjonalnie
szyfrowanie kluczem FIDO2). Treści maili i haseł nie logujemy.

## Stan prac

| Etap | Status |
|---|---|
| Szkielet, konfiguracja, baza SQLite (dedup) | ✅ |
| Parser maili, czyszczenie HTML/cytatów | ✅ |
| Reguły (VIP, słowa kluczowe, blokady, odpowiedzi) | ✅ |
| Klient Ollamy (JSON schema, failover LAN/lokalny), streszczenia | ✅ |
| Pobieranie IMAP, zaległe nieprzeczytane, pipeline, scheduler | ✅ (testy na fake'ach, nie sprawdzone na prawdziwych skrzynkach) |
| Sejf haseł (keyring, opcjonalnie FIDO2) | ⏳ |
| Głos: STT (faster-whisper), TTS (Piper), dialog | ⏳ |
| GUI (PySide6), ustawienia, zasobnik systemowy | ⏳ |
| Pakowanie Windows / Linux | ⏳ |

Szczegółowy plan i decyzje architektoniczne: [`AGENTS.md`](AGENTS.md).

## Uruchomienie (dev)

Wymagany Python 3.12.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m mailvoice   # puste okno (GUI w budowie)
```

Do analizy potrzebny jest działający [Ollama](https://ollama.com) (adres konfigurowalny, domyślnie lokalny z
opcjonalnym drugim serwerem w LAN). Dla polskiego polecany model `qooba/bielik-11b-v3.0-instruct`,
dla angielskiego np. `qwen3:8b`.

## Współpraca

Chętnie przyjmiemy:
- **zgłoszenia błędów** (Issues), szczególnie z różnymi dostawcami poczty (Gmail, Outlook, własne serwery),
- **testy na Windowsie** (audio, mikrofon, FIDO2),
- pomysły na funkcje i **pull requesty**.

Zasady dla kodu: logika w `core/` bez zależności od Qt, każda funkcja z testem, przed PR-em
`ruff check . && python -m pytest -q` musi przejść. Nie zgłaszaj w Issues treści prywatnych maili ani haseł.

## Licencja

GPL-3.0-or-later, zobacz [`LICENSE`](LICENSE).
