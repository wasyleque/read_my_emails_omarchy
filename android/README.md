# MailVoice — aplikacja na Androida / Android app

Companion app for the MailVoice desktop program (pairing by QR code over your own Wi-Fi). **Work in progress** — this
is the project skeleton; pairing, notifications and voice control are planned (see the main README and
`docs/mobile-api.md`).

## Build
Requirements: JDK 17–21 (Gradle 8.7 does not run on newer JDKs), Android SDK with platform 35 and build-tools.

```bash
cd android
export JAVA_HOME=/path/to/jdk21 ANDROID_HOME=$HOME/Android/Sdk
./gradlew :app:assembleDebug          # -> app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```
`local.properties` (SDK path) is not committed; Android Studio creates it, or set `ANDROID_HOME`.

Xiaomi/HyperOS: to install over `adb` enable *Developer options → Install via USB* and *USB debugging (Security
settings)*. For reliable background notifications later, set the app's battery mode to "No restrictions" and enable
autostart.

## Principles
The phone never receives raw mail, attachments or active links — only summaries produced by your computer. Backups are
disabled (`allowBackup=false`) and cleartext traffic is off. See [`SECURITY.md`](../SECURITY.md).
