# MailVoice — aplikacja na Androida

[🇬🇧 English](README.md) · **🇵🇱 Polski**

Aplikacja towarzysząca programowi MailVoice na komputerze (parowanie kodem QR przez Twoją własną sieć Wi-Fi / LAN).

---

## 0. Gotowy plik APK (bez budowania)

1. Pobierz `MailVoice-0.1.0-beta.apk` z [wydania Android](../../../releases/tag/android-v0.1.0-beta) i porównaj jego
   SHA-256 z podanym w opisie wydania (`sha256sum MailVoice-0.1.0-beta.apk`).
2. **Przez USB:** włącz *Opcje programisty → Debugowanie USB*, podłącz telefon i uruchom
   `adb install -r MailVoice-0.1.0-beta.apk`. **Albo na telefonie:** otwórz plik i zezwól na instalowanie nieznanych aplikacji.
3. Uruchom program MailVoice na komputerze, włącz serwer dla telefonu (Ustawienia → Telefon), pokaż kod QR i zeskanuj
   go w aplikacji. Aplikacja wymaga programu na komputerze — sama nie działa.

APK jest podpisany kluczem wydań projektu (SHA-256 certyfikatu
`1068d504bbd87568509a3c90d136be075c069cc9c9e93b8119ca27fba19cd97f`). To **nie** jest wersja ze sklepu Google Play.
Aktualizacje muszą być podpisane tym samym kluczem; jeśli wcześniej zbudowałeś własny APK debug, najpierw go odinstaluj
(sparujesz telefon ponownie). Uprawnienia: aparat (QR), mikrofon (komendy głosowe), powiadomienia, usługa w tle
(odbieranie alertów) oraz prośby o „uruchamianie przy starcie” i wyłączenie optymalizacji baterii, żeby alerty docierały.

---

## 1. Wymagania i budowanie

- **JDK**: Temurin 21 (`mise where java@temurin-21`)
- **Android SDK**: compileSdk 35, minSdk 26, build-tools
- **Gradle**: 8.7, AGP 8.5.2, Kotlin 1.9.24, Compose BOM 2024.06.00 (Compose compiler 1.5.14)
- **Ważne ograniczenie RAM**: Z powodu ograniczeń pamięci maszyny buduj **zawsze maksymalnie jedno zadanie Gradle naraz**, nigdy równolegle.

### Uruchomienie testów jednostkowych JVM:
```bash
cd android
export JAVA_HOME=$(mise where java@temurin-21) ANDROID_HOME=$HOME/Android/Sdk
nice -n 10 ./gradlew :app:testDebugUnitTest --console=plain
```

### Budowanie pakietu APK (Debug):
```bash
cd android
export JAVA_HOME=$(mise where java@temurin-21) ANDROID_HOME=$HOME/Android/Sdk
nice -n 10 ./gradlew :app:assembleDebug --console=plain
# Wynik: app/build/outputs/apk/debug/app-debug.apk
```

### Instalacja na telefonie (ADB):
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```
*Uwaga dla telefonów Xiaomi / Poco (HyperOS / MIUI)*: W opcjach programisty włącz *Instaluj przez USB* oraz *Debugowanie USB (Ustawienia zabezpieczeń)*. Dla niezawodnego działania wyłącz optymalizację baterii (tryb „Bez ograniczeń”) i zezwól na autostart.

---

## 2. Zależności i uzasadnienie

Wszystkie zależności zostały dobrane pod kątem stabilności, bezpieczeństwa offline oraz kompatybilności z Kotlin 1.9.24:

1. **`com.squareup.okhttp3:okhttp:4.12.0`**:
   - Bezpieczna konfiguracja `SSLSocketFactory` i `X509TrustManager` per-klient, bez modyfikowania globalnego stanu maszyny JVM (w przeciwieństwie do `HttpsURLConnection.setDefaultSSLSocketFactory`).
   - Wymuszenie protokołów TLS 1.2 i TLS 1.3 (`ConnectionSpec.MODERN_TLS`).
   - Pula połączeń, precyzyjne limity czasu (timeouts) oraz natywne wsparcie dla WebSockets (WSS).
2. **`com.google.mlkit:barcode-scanning:17.3.0` (wersja standalone z wbudowanym modelem)**:
   - Działa całkowicie **offline**, w lokalnej sieci LAN bez konieczności pobierania modeli z internetu.
   - Działa na telefonach bez Usług Google Play (de-Googled, MicroG, VPN).
3. **`androidx.camera:camera-camera2:1.3.4`**, **`camera-lifecycle:1.3.4`**, **`camera-view:1.3.4`**:
   - Oficjalna biblioteka CameraX do strumieniowania klatek podglądu i analizy obrazu QR w Jetpack Compose.
4. **`androidx.lifecycle:lifecycle-viewmodel-compose:2.8.3`**:
   - Integracja architektury MVVM z Jetpack Compose.
5. **Zależności testowe**:
   - `junit:4.13.2` — testy jednostkowe na JVM.
   - `com.squareup.okhttp3:mockwebserver:4.12.0` + `okhttp-tls:4.12.0` — lokalny serwer testowy TLS z generowaniem certyfikatów w testach JVM.
   - `org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1` — deterministyczne testowanie asynchronicznego kodu w ViewModel i repozytorium.
   - `org.json:json:20240303` — obsługa JSON w testach JVM bez narzutu frameworka Android.

---

## 3. Architektura bezpieczeństwa (B1: Parowanie i połączenie)

Zgodnie z zasadami w [`SECURITY.md`](../SECURITY.pl.md):
- **Certificate Pinning**: Akceptowany jest wyłącznie certyfikat serwera, którego skrót SHA-256 (DER) odpowiada odciskowi z kodu QR. Porównanie jest stałoczasowe (`MessageDigest.isEqual`), chroniąc przed atakami timingowymi.
- **Brak ruchu nieszyfrowanego**: `cleartextTrafficPermitted=false`, wymuszenie HTTPS/TLS 1.2+, odrzucanie żądań HTTP.
- **Bezpieczny magazyn poświadczeń (`KeystoreTokenStore`)**: Token Bearer i odcisk serwera są szyfrowane algorytmem AES-256-GCM kluczem sprzętowym z `AndroidKeyStore`. Wektor IV (12 bajtów) generowany jest losowo przy każdym zapisie. Kopie zapasowe są wyłączone (`allowBackup="false"`).
- **Zasady prywatności**: Tokeny i dane uwierzytelniające nigdy nie trafiają do logów systemowych (`android.util.Log`). Surowe treści e-mail oraz załączniki nigdy nie są pobierane ani przetwarzane przez telefon.
- **Zasady UX**: Interfejs krok po kroku z instrukcją 1-2-3, celownikiem skanera, możliwością ręcznego wpisania parametrów, przyjaznymi komunikatami błędów po polsku i angielsku (i18n).

---

## 4. Architektura poczty i głosu (B2: Poczta, Digest i asystent głosowy)

- **Klient API (`MailApi`)**:
  - Obsługuje zapytania do endpointów REST serwera: `GET /v1/mails/important`, `GET /v1/mails/{id}/summary`, `POST /v1/mails/{id}/ack`, `GET /v1/digest`, `POST /v1/voice/command`, `GET /v1/status`.
  - Wszystkie żądania autoryzowane nagłówkiem `Authorization: Bearer <token>`.
  - Przy błędzie `401 Unauthorized` token jest natychmiast usuwany z telefonu, a aplikacja bezpiecznie powraca do ekranu parowania.
- **Antyphishing i izolacja niebezpiecznych treści**:
  - Wiadomości podejrzane (`suspicious == true`) mają całkowicie zablokowaną treść i streszczenie. Aplikacja nie pozwala na ich odsłuchanie głosem ani nie wyświetla linków.
  - Przed odczytaniem czegokolwiek przez syntezator mowy (`TextToSpeech`), tekst jest przetwarzany przez `UrlSanitizer.prepareForSpeech()`, który usuwa wszystkie odnośniki i zastępuje je naturalną frazą „odnośnik pominięty”.
- **Asystent głosowy i przepływ „Czytać dalej?”**:
  - Maszyna stanów `VoiceSessionController` zarządza kolejką czytania, pytaniem „Czytać dalej?” i nasłuchem komend użytkownika.
  - **Kluczowa zasada bezpieczeństwa**: Komendy wysyłane do `/v1/voice/command` pochodzą **WYŁĄCZNIE z mikrofonu użytkownika** (STT), nigdy z treści maila.
  - Słuchanie opiera się na `SpeechRecognizer` (z preferencją trybu on-device od API 31+). Aplikacja nie wymaga Usług Google Play i oferuje pełne przyciski dotykowe jako alternatywę w głośnym otoczeniu.
  - Uprawnienie `RECORD_AUDIO` jest żądane z wyjaśnieniem wyłącznie przy pierwszym użyciu mikrofonu.
  - Widoczność pakietów na Androidzie 11+ jest zadeklarowana w `<queries>` dla `android.speech.RecognitionService` oraz `android.intent.action.TTS_SERVICE`.

---

## 5. Ignorowanie wiadomości i reguły (B3: Przycisk „Ignoruj…”)

- **Integracja API (`POST /v1/mails/{id}/ignore`)**:
  - Obsługa trzech trybów ignorowania:
    1. `similar` (domyślny) — podobne maile od tego samego nadawcy (ten sam temat bazowy).
    2. `sender` — wszystkie maile od danego nadawcy.
    3. `domain` — wszystkie maile z danej domeny (całej organizacji).
  - Model odpowiedzi: `status`, `mode`, `rule`.
- **Interfejs użytkownika (UX „dla opornych”)**:
  - Dedykowany przycisk „Ignoruj…” dostępny na każdej karcie maila na liście oraz na ekranie szczegółów.
  - Przycisk jest w pełni dostępny również dla maili podejrzanych (`suspicious == true`), stanowiąc zalecaną, bezpieczną reakcję na próby wyłudzenia danych.
  - Okno dialogowe (`IgnoreMailDialog`) z trzema opcjami wyboru (Radio), podglądem nadawcy i tematu, blokadą ponownych kliknięć podczas wysyłania żądania oraz czytelnym wyjaśnieniem, że komputer zapamiętuje regułę i można ją edytować/usunąć w Ustawieniach na komputerze.
  - Po zatwierdzeniu: natychmiastowe usunięcie pozycji z lokalnego widoku, powiadomienie „Zignorowano” (Toast) oraz automatyczne odświeżenie listy z serwera w celu zsynchronizowania innych wiadomości objętych nowo utworzoną regułą.
  - Przyjazna obsługa błędów (400, 404, 503, brak sieci) w języku polskim z możliwością natychmiastowego ponowienia próby, a przy błędzie autoryzacji (401) automatyczny powrót do ekranu parowania.

## 5a. Oznaczanie VIP (B5: Przycisk „VIP…”) — lustro „Ignoruj…”

- **API (`POST /v1/mails/{id}/vip`)**: te same trzy tryby (`similar` / `sender` / `domain`) i ten sam model odpowiedzi.
  Komputer zapamiętuje regułę VIP: takie maile zawsze powiadamiają, a wątki z nimi są pierwsze w podsumowaniu.
- **Interfejs**: przycisk „VIP…” obok „Ignoruj…” na liście i w szczegółach; to samo okno wyboru (`MailRuleDialog`, rodzaj
  `VIP`/`IGNORE`) z tekstami VIP. Dla maili podejrzanych (⚠) przycisk jest **ukryty** (podrobiony nadawca nie zostaje VIP-em
  jednym kliknięciem; ViewModel dodatkowo odrzuca takie żądanie). Po sukcesie: „Oznaczono jako VIP” i odświeżenie listy.
- **Podsumowanie („Sprawy”)**: opcjonalne pole `vip` → znaczek „★ VIP”; limit tematów liczony jest osobno w każdej grupie
  statusu (duża grupa „czeka na mnie” nie wypycha „czeka na innych”).
- `UiWiringTest` pilnuje, żeby akcje ViewModelu były faktycznie podpięte w `MainActivity`.

---

## 6. Obsługa stanów ekranu i podsumowanie spraw (B4: Sprawy i odporność UI)

- **Jawne stany ekranu (`MailsUiState`, `DigestUiState`)**:
  - Wszystkie listy operują na modelu stanów: `Loading`, `Content`, `Empty`, `Error`.
  - Komunikat stanu pustego (np. „Brak ważnych maili”, „Brak aktywnych spraw w wybranym okresie”) wyświetlany jest **wyłącznie po udanym pobraniu pustej listy** (HTTP 200).
  - W razie błędu sieciowego, przekroczenia limitu czasu (timeout), błędu serwera (5xx), limitu zapytań (429) lub parsowania, użytkownik otrzymuje czytelny komunikat po polsku z przyciskiem „Spróbuj ponownie”.
  - Odświeżenie listy z błędem **nie kasuje** wcześniej pobranych wiadomości/spraw — prezentowana jest dotychczasowa lista wraz z banerem błędu u góry.
- **Optymalizacja podsumowania tematów (`GET /v1/digest`)**:
  - Dedykowany limit czasu odczytu 30 s dla zapytania digestu bez modyfikacji limitu globalnego.
  - Domyślne parametry: `GET /v1/digest?days=30&limit=60` zwracające tylko sprawy otwarte.
  - Rozszerzenie modelu `TopicDigest` o pola `counts` (mapa liczników statusów), `total` i `shown` (z pełną odpornością na brak tych pól przy starszych wersjach serwera).
  - Nagłówek z licznikami spraw: „Czeka na Ciebie: X · Czeka na innych: Y”.
  - Przycisk oraz przełącznik „Pokaż także zamknięte i informacyjne (N)” doładowujący sprawy zamknięte i informacyjne (`all=1&limit=100`), z notatką gdy `shown < total` („Pokazano X z Y tematów”).
  - Wskaźnik ładowania z informacją: „Przygotowuję podsumowanie… Pierwsze ładowanie może potrwać kilka sekund”.
