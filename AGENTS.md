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

## Zasady UX (wymóg użytkownika: interfejs „dla opornych”)
- Pierwsze uruchomienie = **kreator krok po kroku** (konta -> test połączenia -> opis „co jest dla mnie ważne” -> głos -> gotowe).
- Dodawanie konta: wybór dostawcy z listy (Gmail, Outlook, inny); serwery/porty/TLS uzupełniane automatycznie, „Zaawansowane” schowane.
- Przycisk „Sprawdź połączenie” przy kontach i przy Ollamie; wynik prostym językiem (nie „IMAP4 LOGIN failed”, tylko „Hasło nie pasuje. Dla Gmaila potrzebne jest hasło aplikacji — pokażę jak”).
- Ollama: automatyczne wykrycie, a gdy brak — prosta instrukcja instalacji i polecany model; bez ręcznego wpisywania URL-i na starcie.
- Opis analizy: gotowe szablony do wyboru („Praca”, „Dom”, „Firma”) + pole własne; zero pojęć typu prompt/LLM/threshold (suwak „jak ostro oceniać”).
- Duże czytelne przyciski, jedna rzecz na ekranie, podpowiedzi, wersje PL/EN interfejsu, sensowne domyślne, wszystko odwracalne.
- Błędy zawsze po ludzku, z przyciskiem „Spróbuj ponownie” i „Co to znaczy?”; nigdy surowe wyjątki ani stack trace.
- Głos jest głównym kanałem: krótkie, naturalne zdania, możliwość „powtórz”, „głośniej”, „wycisz”.
- Dostępność: skróty klawiszowe, kontrast, skalowanie czcionki.

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
- [x] E7 voice/tts.py (Piper PL+EN), voice/beeper.py.
- [x] E8 voice/stt.py (faster-whisper + VAD, push-to-talk), voice/dialog.py (tak/nie/czytaj/następny/pomiń, PL+EN).
- [x] E9 ui: okno główne, zasobnik, lista ważnych maili + uzasadnienie.
- [x] E10 ui: ustawienia (konta, opis analizy, VIP/słowa, interwał, tryb powiadomień, endpointy Ollama, głos).
- [ ] E11 Integracja end-to-end + test na prawdziwej skrzynce (tylko odczyt).
- [ ] E12 Pakowanie Windows/Linux.
- [x] E13 Podsumowanie tematów (Digest), karty kontaktu (Contacts) i inteligentne wyszukiwanie wiadomości (AI Search) + GUI + głos.

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

Decyzje z etapu E7-E10 (batch 3):
- Głos (`src/mailvoice/voice/`): protokoły `Speaker`, `Listener`, `Beeper`, maszyna stanów `VoiceDialog` z normalizacją wypowiedzi (NFKD + zamiana znaku 'ł'/'Ł'), obsługa komend (tak/nie/następny/powtórz/pomiń/stop/głośniej/ciszej), hak `confirm_presence` dla FIDO2. Leniwe importy `piper`, `sounddevice`, `faster-whisper`.
- GUI (`src/mailvoice/ui/`): brak logiki biznesowej w widżetach, cała komunikacja przez `MailService` i zdarzenia `ServiceEventBridge`. `SetupWizard` krok po kroku wg zasad UX, `MainWindow` ze statusem, tabelą maili, akcją odsłuchania i zasobnikiem systemowym `QSystemTrayIcon`. Tłumaczenia PL+EN w `ui/i18n.py` z testem parytetu kluczy. Tabela dostawców poczty w `core/providers.py` i przyjazne komunikaty błędów w `core/friendly_errors.py`.
- Rzeczy NIE zweryfikowane na fizycznym sprzęcie:
  1. Fizyczny mikrofon/głośnik (zweryfikowano testami Fake* i mockami PySide6).
  2. Zewnętrzna instalacja binarki Piper TTS na systemie hosta.
  3. Środowisko Windows (testowano na Linuxie w trybie offscreen).
  4. Fizyczny klucz FIDO2 (issue #4).

Decyzje z etapu E13 (batch 4):
- Baza i indeks (`mail_index`, SQLite): zachowywanie metadanych i podsumowań każdego maila (z retencją `index_retention_days`). NIGDY nie zapisujemy pełnej treści maila w bazie (zasada prywatności). Wyszukiwanie pełnotekstowe przez wirtualną tabelę FTS5 `mail_fts` z fallbackiem do LIKE.
- Łączenie wątków (`src/mailvoice/core/threading.py`): algorytm `thread_key` oparty najpierw na korzeniu z nagłówków References/In-Reply-To, z fallbackiem na znormalizowany temat bez prefiksów (Re/Odp/Fwd itp.) oraz uczestników w oknie czasowym.
- Podsumowanie tematów (`src/mailvoice/core/digest.py`): budowanie podsumowania tematów za N dni (`digest_days`, domyślnie 30) z cache w SQLite (`topic_digest_cache`). Klasyfikacja statusów ("oczekuje_na_mnie", "oczekuje_na_innych", "informacyjne", "zamknięte") na podstawie ostatniego nadawcy w relacji do adresów użytkownika.
- Karty kontaktu (`src/mailvoice/core/contacts.py`): identyfikacja nadawców po adresach, nazwach i aliasach (`contacts`, `contact_addresses`). Generowanie kart `ContactCard` ze statusem relacji, otwartymi sprawami i historią wymiany. Cache w SQLite (`contact_card_cache`).
- Inteligentne wyszukiwanie (`src/mailvoice/core/aisearch.py`): pipeline oparty na zapytaniach w języku naturalnym, LLM query expansion (synonimy, nadawcy, słowa kluczowe), wyszukiwaniu kandydatów w SQLite FTS5 i re-rankingu LLM z przypisaniem pewności (wysoka, średnia, niska). Dociąganie pełnej treści maila z IMAP tylko na żądanie dla pojedynczego podglądu (BODY.PEEK).
- Głos i GUI: komendy mowy dla digestu ("podsumuj miesiąc/tydzień"), kontaktów ("kim jest...", "co z...") oraz wyszukiwania ("znajdź mail..."). W GUI: zakładka "Podsumowanie tematów" (karty spraw z grupami UX), panel "Kontekst nadawcy" w widoku wiadomości (z informacją o nieznanym kontakcie i podpowiedziami) oraz dedykowany dialog "Wyszukiwanie wiadomości (AI)". Pełna obsługa i18n (PL/EN) z parytetem kluczy i zrzuty ekranu w `docs/screenshots/`.

Decyzje z etapu naprawy indeksu i dwukierunkowości (batch 5):
- Dwukierunkowy indeks wiadomości (`mail_index`): dodano kolumnę `direction` ('in' | 'out', domyślnie 'in') z automatyczną migracją istniejących baz bez utraty danych.
- Pipeline pobiera i indeksuje wiadomości wysłane z folderu Wysłane (`fetch_sent_for_index`) z `direction='out'`, `importance=0`, pustym `why`/`summary`, bez wywoływania LLM (tani i szybki zapis), z `recipients` (To+Cc) oraz kluczem wątku `thread_key`. Wiadomości wychodzące nie trafiają do analizy ważności ani do zdarzeń powiadomień. Pełna treść nie jest zapisywana w bazie (ochrona prywatności).
- Automatyczne dopasowanie folderu Wysłane (`providers.COMMON_SENT_FOLDERS`, m.in. "[Gmail]/Sent Mail", "Sent Items", "Wysłane", "Elementy wysłane", "INBOX.Sent" itp.) w przypadku braku lub odmiennej konfiguracji. Błąd braku folderu jest formatowany po ludzku przez `friendly_errors`, a cykl pobierania kontynuuje działanie dla pozostałych folderów.
- Idempotencja indeksowania: `store.is_indexed` sprawdza zarówno klucz złożony (account, folder, uidvalidity, uid), jak i Message-ID, zapobiegając duplikatom przy powtarzanych cyklach.
- Precyzyjny status wątku w `digest.py`: jeśli ostatnia wiadomość w wątku to `direction='out'`, wątek otrzymuje status `oczekuje_na_innych`; jeśli ostatnia wiadomość to `direction='in'` od kontrahenta — `oczekuje_na_mnie`. Zachowano fallback po `user_addrs` dla starszych wpisów.
- Inwalidacja cache podsumowania tematów (`store.invalidate_topic_digest_cache`) przy zaindeksowaniu nowej wiadomości (przychodzącej lub wychodzącej), gwarantująca natychmiastowe przejście wątku do właściwego stanu po wysłaniu odpowiedzi przez użytkownika.
- Wymiany dwukierunkowe w `digest.py` i `contacts.py`: formatowanie "Ty → Odbiorca" oraz "Nadawca → Ty".
- Karta kontaktu (`contacts.py`): otwarte sprawy rozróżniają stan oczekiwania ("Czeka na Ciebie: ..." vs "Czeka na kontakt (Nazwa): ..."). `last_contact` jest wyznaczany z obu kierunków, a kontakty są rozpoznawane również z nagłówków `recipients` wiadomości wychodzących.

