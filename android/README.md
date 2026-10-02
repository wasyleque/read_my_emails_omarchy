# MailVoice — aplikacja na Androida / Android app

Companion app for the MailVoice desktop program (pairing by QR code over your own Wi-Fi / local network).

---

## 1. Wymagania i budowanie / Build requirements

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

## 2. Zależności i uzasadnienie / Dependencies & Rationale

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

Zgodnie z zasadami w [`SECURITY.md`](../SECURITY.md):
- **Certificate Pinning**: Akceptowany jest wyłącznie certyfikat serwera, którego skrót SHA-256 (DER) odpowiada odciskowi z kodu QR. Porównanie jest stałoczasowe (`MessageDigest.isEqual`), chroniąc przed atakami timingowymi.
- **Brak ruchu nieszyfrowanego**: `cleartextTrafficPermitted=false`, wymuszenie HTTPS/TLS 1.2+, odrzucanie żądań HTTP.
- **Bezpieczny magazyn poświadczeń (`KeystoreTokenStore`)**: Token Bearer i odcisk serwera są szyfrowane algorytmem AES-256-GCM kluczem sprzętowym z `AndroidKeyStore`. Wektor IV (12 bajtów) generowany jest losowo przy każdym zapisie. Kopie zapasowe są wyłączone (`allowBackup="false"`).
- **Zasady prywatności**: Tokeny i dane uwierzytelniające nigdy nie trafiają do logów systemowych (`android.util.Log`). Surowe treści e-mail oraz załączniki nigdy nie są pobierane ani przetwarzane przez telefon.
- **Zasady UX**: Interfejs krok po kroku z instrukcją 1-2-3, celownikiem skanera, możliwością ręcznego wpisania parametrów, przyjaznymi komunikatami błędów po polsku i angielsku (i18n).
