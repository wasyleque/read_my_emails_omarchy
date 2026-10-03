# MailVoice — Android app

**🇬🇧 English** · [🇵🇱 Polski](README.pl.md)

Companion app for the MailVoice desktop program (pairing by QR code over your own Wi-Fi / local network).

---

Created by **wasyleque** · [Project on GitHub](https://github.com/wasyleque/read_my_emails_omarchy) · If you like
it, the app's Settings screen has a "♥ If you like it, please donate" button (PayPal, optional).

## 0. Install a ready-made APK (no building)

1. Download `MailVoice-0.1.1-beta.apk` from the [Android release](../../../releases/tag/android-v0.1.1-beta) and
   compare its SHA-256 with the one in the release notes (`sha256sum MailVoice-0.1.1-beta.apk`).
2. **Over USB:** enable *Developer options → USB debugging*, connect the phone and run
   `adb install -r MailVoice-0.1.1-beta.apk`. **Or on the phone:** open the file and allow "install unknown apps".
3. Start the MailVoice desktop program, enable the phone server (Settings → Phone), show the QR code and scan it
   in the app. The app needs the desktop program — it does not work on its own.

The APK is signed with the project's release key (certificate SHA-256
`1068d504bbd87568509a3c90d136be075c069cc9c9e93b8119ca27fba19cd97f`). It is **not** from Google Play. Updates must
be signed with the same key; if you built your own debug APK earlier, uninstall it first (you will pair again).
Permissions: camera (QR), microphone (voice commands), notifications, a foreground service (receiving alerts in the
background), and "run at boot"/"ignore battery optimisation" requests so alerts keep arriving.

---

## 1. Requirements and building

- **JDK**: Temurin 21 (`mise where java@temurin-21`)
- **Android SDK**: compileSdk 35, minSdk 26, build-tools
- **Gradle**: 8.7, AGP 8.5.2, Kotlin 1.9.24, Compose BOM 2024.06.00 (Compose compiler 1.5.14)
- **Memory limit**: because of RAM limits on the dev machine, run **at most one Gradle task at a time**, never in parallel.

### Run the JVM unit tests
```bash
cd android
export JAVA_HOME=$(mise where java@temurin-21) ANDROID_HOME=$HOME/Android/Sdk
nice -n 10 ./gradlew :app:testDebugUnitTest --console=plain
```

### Build the debug APK
```bash
cd android
export JAVA_HOME=$(mise where java@temurin-21) ANDROID_HOME=$HOME/Android/Sdk
nice -n 10 ./gradlew :app:assembleDebug --console=plain
# Output: app/build/outputs/apk/debug/app-debug.apk
```

### Install on a phone (ADB)
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```
*Xiaomi / Poco phones (HyperOS / MIUI):* in Developer options enable *Install via USB* and *USB debugging
(Security settings)*. For reliable background notifications disable battery optimisation ("No restrictions") and
allow autostart.

---

## 2. Dependencies and rationale

All dependencies were chosen for stability, offline security and compatibility with Kotlin 1.9.24:

1. **`com.squareup.okhttp3:okhttp:4.12.0`**
   - Per-client `SSLSocketFactory` and `X509TrustManager`, without touching global JVM state (unlike
     `HttpsURLConnection.setDefaultSSLSocketFactory`).
   - TLS 1.2 and 1.3 only (`ConnectionSpec.MODERN_TLS`).
   - Connection pool, precise timeouts and native WebSocket (WSS) support.
2. **`com.google.mlkit:barcode-scanning:17.3.0` (standalone, bundled model)**
   - Works fully **offline** on the local network, no model download needed.
   - Works on phones without Google Play Services (de-Googled, MicroG, VPN).
3. **`androidx.camera:camera-camera2:1.3.4`**, **`camera-lifecycle:1.3.4`**, **`camera-view:1.3.4`**
   - Official CameraX library for the preview stream and QR image analysis in Jetpack Compose.
4. **`androidx.lifecycle:lifecycle-viewmodel-compose:2.8.3`**
   - MVVM integration with Jetpack Compose.
5. **Test dependencies**
   - `junit:4.13.2` — JVM unit tests.
   - `com.squareup.okhttp3:mockwebserver:4.12.0` + `okhttp-tls:4.12.0` — a local TLS test server with certificates
     generated inside the tests.
   - `org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1` — deterministic testing of async code in ViewModels.
   - `org.json:json:20240303` — JSON in JVM tests without the Android framework.

---

## 3. Security architecture (B1: pairing and connection)

Following the rules in [`SECURITY.md`](../SECURITY.md):
- **Certificate pinning**: only the server certificate whose SHA-256 (DER) fingerprint matches the one from the QR
  code is accepted. The comparison is constant-time (`MessageDigest.isEqual`) to resist timing attacks.
- **No cleartext traffic**: `cleartextTrafficPermitted=false`, HTTPS/TLS 1.2+ enforced, plain HTTP rejected.
- **Secure credential store (`KeystoreTokenStore`)**: the Bearer token and server fingerprint are encrypted with
  AES-256-GCM using a hardware-backed `AndroidKeyStore` key. A fresh random 12-byte IV is used for every write.
  Backups are disabled (`allowBackup="false"`).
- **Privacy**: tokens and credentials never reach the system log (`android.util.Log`). Raw e-mail content and
  attachments are never downloaded or processed by the phone.
- **UX**: step-by-step 1-2-3 instructions, a scanner viewfinder, manual entry of the parameters, friendly error
  messages in Polish and English (i18n).

---

## 4. Mail and voice architecture (B2: mail, digest and voice assistant)

- **API client (`MailApi`)**
  - Calls the server's REST endpoints: `GET /v1/mails/important`, `GET /v1/mails/{id}/summary`,
    `POST /v1/mails/{id}/ack`, `GET /v1/digest`, `POST /v1/voice/command`, `GET /v1/status`.
  - Every request carries `Authorization: Bearer <token>`.
  - On `401 Unauthorized` the token is removed from the phone immediately and the app returns to the pairing screen.
- **Anti-phishing and isolation of dangerous content**
  - Suspicious mail (`suspicious == true`) has its body and summary fully blocked. The app neither reads it aloud nor
    shows its links.
  - Before anything goes to the speech synthesiser (`TextToSpeech`), the text is run through
    `UrlSanitizer.prepareForSpeech()`, which removes every link and replaces it with a natural phrase ("link omitted").
- **Voice assistant and the "Continue reading?" flow**
  - The `VoiceSessionController` state machine manages the reading queue, the "Continue reading?" question and
    listening for user commands.
  - **Key safety rule**: commands sent to `/v1/voice/command` come **ONLY from the user's microphone** (speech
    recognition), never from mail content.
  - Listening uses `SpeechRecognizer` (on-device mode preferred from API 31). The app does not need Google Play
    Services and offers full touch buttons as an alternative in noisy places.
  - The `RECORD_AUDIO` permission is requested, with an explanation, only on first use of the microphone.
  - Package visibility on Android 11+ is declared in `<queries>` for `android.speech.RecognitionService` and
    `android.intent.action.TTS_SERVICE`.

---

## 5. Ignoring mail and rules (B3: the "Ignore…" button)

- **API (`POST /v1/mails/{id}/ignore`)**
  - Three modes:
    1. `similar` (default) — similar mail from the same sender (same base subject).
    2. `sender` — all mail from the sender.
    3. `domain` — all mail from the domain (the whole organisation).
  - Response model: `status`, `mode`, `rule`.
- **User interface ("for dummies" UX)**
  - A dedicated "Ignore…" button on every mail card in the list and on the detail screen.
  - It is fully available for suspicious mail too, as the recommended safe reaction to phishing attempts.
  - A dialog (`IgnoreMailDialog`) with three radio options, a preview of the sender and subject, controls locked
    while the request is in flight, and a clear note that the computer remembers the rule and it can be edited or
    removed in the desktop Settings.
  - After confirming: the item disappears from the local view immediately, an "Ignored" toast appears and the list
    is refreshed from the server so other mail covered by the new rule is synchronised.
  - Friendly errors (400, 404, 503, no network) in Polish with an immediate retry; on an authorisation error (401)
    the app returns to the pairing screen.

## 5a. Marking VIP (B5: the "VIP…" button) — the mirror of "Ignore…"

- **API (`POST /v1/mails/{id}/vip`)**: the same three modes (`similar` / `sender` / `domain`) and response model.
  The computer remembers the VIP rule: such mail always notifies, and threads with it come first in the digest.
- **Interface**: a "VIP…" button next to "Ignore…" on the list and detail screens, using the same dialog
  (`MailRuleDialog`, kind `VIP`/`IGNORE`) with VIP wording. For suspicious mail (⚠) the button is **hidden** (a forged
  sender cannot become a VIP with one click; the ViewModel also rejects such a request). After success: "Marked as
  VIP" and a list refresh.
- **Digest ("Matters")**: the optional `vip` field shows a "★ VIP" badge; the topic limit is applied per status
  group (a large "waiting for me" group does not push out "waiting for others").
- `UiWiringTest` makes sure the ViewModel actions are actually wired up in `MainActivity`.

---

## 6. Screen states and the matters digest (B4: "Matters" and UI resilience)

- **Explicit screen states (`MailsUiState`, `DigestUiState`)**
  - All lists use a state model: `Loading`, `Content`, `Empty`, `Error`.
  - An empty-state message (e.g. "No important mail", "No active matters in the chosen period") is shown **only
    after a successful fetch of an empty list** (HTTP 200).
  - On a network error, timeout, server error (5xx), rate limit (429) or parse error the user gets a clear message
    with a "Try again" button.
  - A failed refresh **does not clear** previously loaded mail/matters — the existing list stays with an error
    banner on top.
- **Digest optimisation (`GET /v1/digest`)**
  - A dedicated 30 s read timeout for the digest request, without changing the global timeout.
  - Default parameters: `GET /v1/digest?days=30&limit=60`, returning open matters only.
  - `TopicDigest` carries `counts` (status counters), `total` and `shown`, tolerating their absence on older servers.
  - A header with counters: "Waiting for you: X · Waiting for others: Y".
  - A button/toggle "Also show closed and informational (N)" that loads them (`all=1&limit=100`), with a note when
    `shown < total` ("Showing X of Y topics").
  - A loading indicator: "Preparing the summary… The first load may take a few seconds".
