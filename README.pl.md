# MailVoice (read_my_emails_omarchy)

[🇬🇧 English](README.md) · **🇵🇱 Polski**

> 🚧 **Projekt roboczy.** Rdzeń logiki, GUI i warstwa głosowa istnieją i mają testy, ale aplikacja **nie była jeszcze
> uruchomiona na prawdziwych skrzynkach**, a mikrofon/głośnik, Windows i sprzętowy klucz FIDO2 są **nieprzetestowane**.
> Zgłoszenia błędów i pull requesty są bardzo mile widziane.

Aplikacja desktopowa na **Linuksa (tworzona z myślą o [Omarchy](https://omarchy.org)) i Windows**: pobiera pocztę z kilku
skrzynek IMAP, **lokalny model AI (Ollama)** ocenia, które nowe wiadomości naprawdę są dla Ciebie ważne, a program
informuje o nich **głosem po polsku lub angielsku** — streszczeniem w 3–4 zdaniach zamiast czytania całego maila.
Ma być obsługiwalna także dla osób niezaawansowanych technicznie.

Poczta nie opuszcza Twojego komputera: analiza działa na **Twoim własnym serwerze Ollama** (lokalnym lub w sieci LAN).

## Co potrafi

- **Kilka skrzynek** (Gmail, Outlook/Microsoft 365, WP, Onet, O2, Interia, dowolny serwer IMAP).
- **Analizuje tylko nowe maile.** Już widziane są pomijane w kolejnych cyklach (śledzenie UID + deduplikacja po
  `Message-ID`, odporność na reset `UIDVALIDITY`).
- **„Co jest dla mnie ważne” własnymi słowami.** Opisujesz zwykłym językiem, jak oceniać pocztę; dodajesz nadawców VIP,
  słowa kluczowe i blokady; odpowiedzi na wysłane przez Ciebie maile dostają bonus. Najpierw działa tania warstwa
  reguł, resztę ocenia model i zwraca walidowany JSON (ważność 0–10, powód, akcja, język).
- **Powiadomienia głosowe.** Wybierasz: powtarzany sygnał dźwiękowy albo pytanie *„Czy masz teraz czas posłuchać nowych
  maili?”*. Potem czyta krótkie streszczenie (maks. 4 zdania) każdego maila i rozumie komendy *następny / powtórz /
  pomiń / stop* (PL + EN).
- **Zaległe, starsze nieprzeczytane maile.** Jeśli któreś wyglądają na ważne, aplikacja pyta osobno, czy chcesz je
  usłyszeć. Odpowiedź jest zapamiętywana, także po restarcie.
- **Podsumowanie tematów — „łączenie kropek”.** Domyślnie ostatni miesiąc (konfigurowalnie): wątki, kto do kogo pisał,
  dlaczego i czy sprawa czeka na Ciebie, czy na innych. *(Rdzeń gotowy; indeksowanie Twoich wysłanych maili jest
  w trakcie — patrz stan prac.)*
- **Karta kontaktu i „Wyszukaj maila (AI)”.** Pokazuje pełny kontekst osoby, gdy zamierzasz odpisać, i znajduje
  najbardziej prawdopodobne maile z opisu własnymi słowami, z uzasadnieniem i pewnością. *(Stan jak wyżej.)*
- **Prosty kreator konfiguracji**, błędy po ludzku, duże przyciski, interfejs PL/EN.

### Zrzuty ekranu

| Kreator | Okno główne | Ustawienia |
|---|---|---|
| ![Dodaj konto](docs/screenshots/wizard_account.png) | ![Okno główne](docs/screenshots/main_window.png) | ![Ustawienia](docs/screenshots/settings.png) |

| Podsumowanie tematów | Kontekst kontaktu | Wyszukiwanie AI |
|---|---|---|
| ![Podsumowanie](docs/screenshots/main_window_digest.png) | ![Kontekst](docs/screenshots/main_window_context.png) | ![Szukaj](docs/screenshots/search_dialog.png) |

*Zrzuty zrobione w trybie offscreen na danych przykładowych.*

## Prywatność i bezpieczeństwo

- **Tylko odczyt.** Aplikacja niczego nie wysyła, nie usuwa ani nie oznacza jako przeczytane (`BODY.PEEK`).
- **Tylko lokalne AI.** Treść maili trafia wyłącznie do skonfigurowanych przez Ciebie adresów Ollamy.
- **Hasła** są w systemowym keyringu (rezerwa: plik szyfrowany AES-256-GCM z kluczem scrypt; opcjonalnie ochrona kluczem
  FIDO2 `hmac-secret`). Nigdy nie trafiają do pliku konfiguracyjnego ani do logów.
- **TLS jest obowiązkowy** dla IMAP; połączenia nieszyfrowane są odrzucane.
- **Lokalny indeks przechowuje tylko metadane i krótkie podsumowania** (nigdy pełnych treści maili), z limitem retencji
  (`index_retention_days`, domyślnie 90).
- **Zasady antyphishingowe są nienaruszalne** — zob. [`SECURITY.md`](SECURITY.md): aplikacja nigdy nie otwiera
  linków, nie pobiera załączników i nie słucha instrukcji zawartych (także ukrytych) w mailach. *Te zasady są
  kontraktem projektowym; pełne wdrożenie (bezpieczne pobieranie bez załączników, usuwanie ukrytego tekstu, ochrona
  przed prompt injection, ocena ryzyka phishingu) jest **w toku** — śledzone w [#9](../../issues/9).*

## Stan prac

| Obszar | Status |
|---|---|
| Konfiguracja, deduplikacja w SQLite, parser maili, reguły, klient Ollamy z failoverem LAN/lokalny, streszczenia | ✅ |
| Pobieranie IMAP (tylko odczyt, tylko TLS), zaległe nieprzeczytane, pipeline, scheduler, pętla serwisu | ✅ (testowane tylko na atrapach) |
| Sejf haseł: keyring, szyfrowany plik, backend FIDO2 | ✅ (FIDO2 tylko na atrapie urządzenia) |
| Głos: Piper TTS, faster-whisper STT, dialog, beeper | ✅ (atrapy; bez testu na prawdziwym audio) |
| GUI: kreator, okno główne, ustawienia, zasobnik, PL/EN | ✅ (tylko offscreen) |
| Podsumowanie tematów, łączenie wątków, karta kontaktu, wyszukiwanie AI | ✅ rdzeń · ⏳ indeksowanie wysłanych |
| Utwardzenie antyphishingowe | ⏳ w toku ([#9](../../issues/9)) |
| Test na prawdziwych skrzynkach (Gmail/Outlook/własny serwer), Windows, pakowanie (.exe/AppImage) | ⏳ ([#3](../../issues/3)) |

Szczegóły i decyzje architektoniczne: [`AGENTS.md`](AGENTS.md). Otwarte zadania są w [Issues](../../issues) —
kilka nadaje się na dobry początek.

## Instalacja (dla użytkownika)

> Na razie bez gotowego instalatora. Potrzebny Python 3.12.

1. **Ollama** — zainstaluj z [ollama.com](https://ollama.com), potem pobierz model:
   ```bash
   ollama pull qwen3:8b                         # szybki, dobry dla angielskiego
   ollama pull qooba/bielik-11b-v3.0-instruct   # najlepszy dla polskiego
   ```
2. **Piper (mowa, opcjonalnie)** — pobierz binarkę `piper` i głos (np. `pl_PL-darkman-medium` lub głos `en_US`) ze
   [stron wydań Pipera](https://github.com/rhasspy/piper/releases) i dodaj `piper` do `PATH`. Bez Pipera aplikacja
   używa sygnałów dźwiękowych i komunikatów na ekranie.
3. **MailVoice**
   ```bash
   git clone https://github.com/wasyleque/read_my_emails_omarchy.git
   cd read_my_emails_omarchy
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -e ".[voice]"
   python -m mailvoice
   ```
4. Przy pierwszym uruchomieniu startuje kreator krok po kroku: język → konto pocztowe (z testem połączenia) →
   wykrycie Ollamy → co jest dla Ciebie ważne → powiadomienia i test głosu.

**Gmail:** potrzebne jest *hasło aplikacji* (Konto Google → Bezpieczeństwo → Weryfikacja dwuetapowa → Hasła do
aplikacji). Kreator to wyjaśnia. Na początek użyj konta testowego.

## Rozwój

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,voice]"
ruff check . && QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Zasady dla kodu: logika biznesowa w `src/mailvoice/core/` **bez zależności od Qt**; `ui/` bez logiki biznesowej;
backendy głosu za Protocolami, żeby dało się je mockować; każda funkcja ma test; przed PR-em muszą przejść
`ruff check .` i `pytest`. Przeczytaj [`SECURITY.md`](SECURITY.md), zanim zmienisz obsługę poczty.

## Współpraca

- **Zgłoszenia błędów** — szczególnie od różnych dostawców poczty (nazwy folderów, kodowania, `UIDVALIDITY`, OAuth).
- **Testy na Windowsie** — audio, mikrofon, FIDO2.
- **Pomysły na funkcje i pull requesty.**

⚠️ **Nigdy nie wklejaj do issues prawdziwych maili, haseł ani tokenów.** Problemy bezpieczeństwa zgłaszaj prywatnie
przez stronę repozytorium *Security → Report a vulnerability*.

## Licencja

GPL-3.0-or-later — zobacz [`LICENSE`](LICENSE).
