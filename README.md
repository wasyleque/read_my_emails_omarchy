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
| Pobieranie IMAP, zaległe nieprzeczytane, pipeline, scheduler, serwis | ✅ |
| Sejf haseł (KeyringStore, EncryptedFileStore AES-256-GCM, FIDO2 HMAC-secret) | ✅ |
| Głos: TTS (Piper PL/EN), STT (faster-whisper), dialog, komendy, beeper | ✅ (protokoły, fake'i i backendy) |
| GUI (PySide6): kreator startowy, okno główne, zasobnik, i18n PL/EN | ✅ |
| Integracja end-to-end na fizycznej skrzynce / pakowanie (.exe / AppImage) | ⏳ |

Szczegółowy plan i decyzje architektoniczne: [`AGENTS.md`](AGENTS.md).

## Instalacja dla użytkownika

### 1. Pobierz i uruchom Ollamę (Sztuczna Inteligencja)
Pobierz instalator ze strony [ollama.com](https://ollama.com) i zainstaluj program.
W terminalu / wierszu poleceń pobierz polecany model AI:
```bash
ollama run qwen3:8b
# lub polski model:
ollama run qooba/bielik-11b-v3.0-instruct
```

### 2. Synteza mowy (Piper TTS — zalecane)
Aplikacja czyta podsumowania na głos za pomocą szybkiego, lokalnego syntezatora Piper:
- Pobierz binarkę `piper` z [GitHub Piper Releases](https://github.com/rhasspy/piper/releases) i dodaj ją do ścieżki systemowej `PATH`.
- Pobierz model głosu (np. polski `pl_PL-darkman-medium.onnx` wraz z plikiem `.json`).
*(W przypadku braku Pipera aplikacja wyświetla czytelne powiadomienie lub korzysta z sygnałów dźwiękowych).*

### 3. Uruchomienie aplikacji MailVoice
Zainstaluj pakiet z opcjonalnymi zależnościami głosu:
```bash
pip install -e ".[voice]"
python -m mailvoice
```
Przy pierwszym uruchomieniu powita Cię prosty kreator krok po kroku:
1. Wybór języka (Polski / English),
2. Podłączenie konta pocztowego (automatyczne szablony: Gmail, Outlook, WP, Onet, O2, Interia, własny IMAP),
3. Automatyczne wykrycie Ollamy i zainstalowanych modeli,
4. Szablon reguł (Praca / Dom / Firma) oraz suwak ostrości oceny,
5. Wybór powiadomień (pytanie głosowe lub dyskretny beep) i test głosu.

## Uruchomienie (dev)

Wymagany Python 3.12.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,voice]"
ruff check . && python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m mailvoice
```

## Współpraca

Chętnie przyjmiemy:
- **zgłoszenia błędów** (Issues), szczególnie z różnymi dostawcami poczty (Gmail, Outlook, własne serwery),
- **testy na Windowsie** (audio, mikrofon, FIDO2),
- pomysły na funkcje i **pull requesty**.

Zasady dla kodu: logika w `core/` bez zależności od Qt, każda funkcja z testem, przed PR-em
`ruff check . && python -m pytest -q` musi przejść. Nie zgłaszaj w Issues treści prywatnych maili ani haseł.

## Licencja

GPL-3.0-or-later, zobacz [`LICENSE`](LICENSE).
