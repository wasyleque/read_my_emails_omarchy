# MailVoice — reguły projektu (czytaj ZAWSZE przed zmianą kodu)

Aplikacja GUI (Windows + Linux): pobiera pocztę z wielu skrzynek IMAP (Gmail, własny serwer), lokalny model AI
(Ollama) ocenia, które nowe maile są ważne (wg opisu użytkownika, nadawców, słów kluczowych, odpowiedzi na wysłane),
a program informuje głosem (PL/EN): przypomnienie dźwiękowe co N minut LUB pytanie głosowe „czy masz czas wysłuchać?”,
potem streszczenie 3–4 zdania (bez czytania całości). Już pobrane maile ignorujemy w kolejnych cyklach.

## Stos
Python 3.12, PySide6, imap-tools, sqlite3, keyring, httpx (Ollama /api/chat, format=JSON schema),
faster-whisper + silero-vad (STT), Piper (TTS), sounddevice. Testy: pytest. Lint: ruff.
Pakowanie: PyInstaller (.exe) / AppImage — na końcu.

## Architektura (NIE ZMIENIAĆ bez zgody nadzorcy)
- `src/mailvoice/core/` — logika BEZ zależności od Qt: `store.py` (SQLite), `imap_fetch.py`, `rules.py`,
  `analyzer.py`, `summarizer.py`, `scheduler.py`, `config.py`. W pełni testowalne pytest.
- `src/mailvoice/voice/` — `stt.py`, `tts.py`, `dialog.py` (maszyna stanów), `beeper.py`. Za interfejsami (Protocol), by dało się mockować.
- `src/mailvoice/ui/` — tylko PySide6, żadnej logiki biznesowej.
- Deduplikacja: tabela `seen(account, folder, uidvalidity, uid, message_id)`; pobieramy tylko UID > last_uid;
  zmiana UIDVALIDITY = reset folderu (dedup po Message-ID).
- Zaległe (backlog): oprócz nowych, skanujemy wstecz maile ze znacznikiem NIEPRZECZYTANE (IMAP UNSEEN), których jeszcze nie ma w `seen`
  (np. pierwszy start, starsze niż last_uid; zakres wstecz konfigurowalny, domyślnie 30 dni). Przechodzą tę samą analizę. Jeśli któryś jest ważny,
  aplikacja OSOBNO pyta użytkownika (głosem/GUI): „Masz też N ważnych nieprzeczytanych starszych maili — czy chcesz usłyszeć streszczenia?”.
  Odpowiedź nie = zapisujemy jako `seen` z flagą `backlog_declined` (nie pytamy ponownie). Dalej tylko BODY.PEEK — flagi nie zmieniamy.
- Odpowiedzi: folder Wysłane + nagłówki In-Reply-To/References => bonus ważności „odpowiedź na mój mail”.
- Analiza 2-warstwowa: (1) `rules.py` bez LLM (VIP, słowa kluczowe, blokady, odpowiedź), (2) LLM zwraca
  JSON `{importance:0-10, reason, action, language}` (temat+nadawca+pierwsze ~1500 znaków). Streszczenie osobnym wywołaniem, max 4 zdania.
- Ollama: dwa endpointy (LAN `http://192.168.1.50:11434` + lokalny `http://127.0.0.1:11434`), przełączanie/failover, konfigurowalne.
  Modele: domyślnie `qwen3:8b`, PL: `qooba/bielik-11b-v3.0-instruct`.
- Sekrety (hasła/tokeny) tylko w keyring, nigdy w configu ani logach. Treść maili nie trafia do logów.
- Aplikacja NIC nie wysyła, nie usuwa, nie oznacza maili (tylko odczyt, IMAP BODY.PEEK).

## Zasady pracy dla modeli
1. Jedno zadanie = jedna mała zmiana. Nie ruszaj plików spoza zadania.
2. Każda funkcja w `core/` ma test w `tests/`.
3. Przed zakończeniem MUSI przejść: `ruff check . && pytest -q`.
4. Komentarze i teksty UI po polsku (z możliwością tłumaczenia), identyfikatory po angielsku.
5. Nie twierdź, że test przeszedł, jeśli nie widziałeś tego w wyjściu komendy.

## Etapy (status: [ ] do zrobienia, [x] zrobione)
- [x] E0 Szkielet: pyproject, venv (mise python 3.12), struktura katalogów, pytest+ruff, puste okno PySide6.
- [x] E1a core/store.py (SQLite: seen, folder_state) + testy.
- [x] E1b core/config.py (konta, opis analizy, VIP/słowa, interwał, tryb powiadomień, endpointy Ollama) + testy.
- [x] E1c (zrobione) core/secrets.py: Protocol SecretStore + KeyringStore (domyślny) + EncryptedFileStore (AES-256-GCM + scrypt, 0600) + Fido2Store (hmac-secret, wiele kluczy, awaryjna fraza; fake dla testów, fizyczny wymaga testu na Windows issue #4). Wymuszenie SSL/TLS w imap_fetch.
- [x] E2a textutil.py (html_to_text, clean_body, truncate_for_llm) zrobione [x].
- [x] E2b mailparse.py (parse_raw -> ParsedMail; identyfikatory Message-ID z nawiasami <>, daty ze strefą).
- [x] E2 core/imap_fetch.py: pobieranie nowych (UID>last), BODY.PEEK, parser tekstu (HTML->tekst), testy na mocku.
- [x] E2b core/imap_fetch.py: tryb backlog (UNSEEN wstecz N dni, pomijanie już w `seen`) + testy.
- [x] E3 core/rules.py: VIP, słowa kluczowe, blokady, wykrywanie odpowiedzi (Wysłane + nagłówki) + testy.
- [x] E4 core/analyzer.py: klient Ollama, JSON schema, failover LAN/lokalny, prompt z opisem użytkownika + testy (mock httpx).
- [x] E5 core/summarizer.py (3–4 zdania, język maila) + testy.
- [x] E6 core/scheduler.py: cykl co N min, tryby powiadomień (reminder-beep / pytanie głosowe), osobne pytanie o zaległe ważne nieprzeczytane + testy.
- [ ] E7 voice/tts.py (Piper PL+EN), voice/beeper.py.
- [ ] E8 voice/stt.py (faster-whisper + VAD, push-to-talk), voice/dialog.py (tak/nie/czytaj/następny/pomiń, PL+EN).
- [ ] E9 ui: okno główne, zasobnik, lista ważnych maili + uzasadnienie.
- [ ] E10 ui: ustawienia (konta, opis analizy, VIP/słowa, interwał, tryb powiadomień, endpointy Ollama, głos).
- [ ] E11 Integracja end-to-end + test na prawdziwej skrzynce (tylko odczyt).
- [ ] E12 Pakowanie Windows/Linux.

## Podział pracy
Claude = plan, zlecenia, wyrywkowa weryfikacja. agy (prawie tak mądry jak Claude, pane Herdr `w8:p3`) = logika, integracje,
większe etapy (kilka naraz, z samoweryfikacją `ruff check . && pytest -q`). aider+Ollama (qwen3-coder:30b, `scripts/delegate.sh`)
= tylko proste rzeczy: boilerplate, widgety, powtarzalne testy. Doświadczenie: Ollama zostawia błędy logiczne i testy kodujące te same błędy.

## Wznowienie pracy
Backup: `scripts/backup-usb.sh` -> dysk USB SAMSUNG (/run/media/wasyl/SAMSUNG/mailvoice-backup); robić przed przerwami.
Projekt założony 2026-10-02. Decyzje użytkownika: Python+PySide6; Ollama LAN+lokalny z przełączaniem; konta Gmail + własny IMAP;
powiadomienia: reminder dźwiękowy co N min LUB pytanie głosowe; streszczenie max 3–4 zdania; start od E0.

Decyzje z etapu E1c i integracji (batch 2):
- E1c: `SecretStore` z trzema backendami (`KeyringStore`, `EncryptedFileStore` AES-256-GCM + scrypt 0600, `Fido2Store` hmac-secret z wieloma kluczami i frazą ratunkową). Wymuszenie `use_ssl` w IMAP (odmowa połączeń bez TLS/SSL).
- Issue #1: Rozróżnienie `AnalyzerTransportError` (przerwanie folderu i ponowienie) vs `AnalyzerFormatError` (licznik prób w tabeli `analysis_attempts` w SQLite, po 3 próbach `status='failed'`, przesunięcie `last_uid` i przejście dalej).
- Issue #2: Zaległości w stanie oczekiwania są zapisywane ze statusem `backlog_pending`. Funkcja `load_pending_backlog(store)` odtwarza je po restarcie aplikacji. Zapobiega to powtórnemu analizowaniu tych samych zaległości.
- Punkt 4: `MailService` w `src/mailvoice/core/service.py` spina config, secret_store, store, analyzer i scheduler/notifier w pętlę sterowaną z zewnątrz `tick(now)` ze zdarzeniami (`NewImportant`, `BacklogQuestion`, `BeepReminder`, `AskReminder`, `ServiceError`), pobierając hasło tuż przed logowaniem.
- Do weryfikacji sprzętowej: fizyczny klucz FIDO2 na Windowsie/Linuxie (issue #4).
