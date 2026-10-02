# MailVoice (read_my_emails_omarchy)

**🇬🇧 English** · [🇵🇱 Polski](README.pl.md)

> 🚧 **Work in progress.** The core logic, GUI, voice layer and the Android companion are covered by tests and have been
> **partially tested on live mailboxes** (IMAP fetching, AI analysis, voice, phone pairing and notifications on Linux/Omarchy
> + an Android 14 phone). **Windows, hardware FIDO2 keys and more mail providers are still untested.**
> Bug reports and pull requests are very welcome.

A desktop app for **Linux (built for [Omarchy](https://omarchy.org)) and Windows** that fetches mail from several IMAP
accounts, lets a **local AI model (Ollama)** decide which new messages really matter to you, and tells you about them
**by voice, in Polish or English** — with a 3–4 sentence summary instead of reading the whole mail.
It is designed to be usable by people who are not technical.

Your mail never leaves your machine: analysis runs on **your own Ollama server** (local or on your LAN).

## What it does

- **Several mailboxes** (Gmail, Outlook/Microsoft 365, WP, Onet, O2, Interia, any IMAP server).
- **Only new mail is analysed.** Already-seen messages are skipped in every later cycle (UID tracking + `Message-ID`
  de-duplication, safe against `UIDVALIDITY` resets).
- **"What matters to me" in your own words.** You describe in plain language how to judge mail; add VIP senders, keywords
  and blocked senders; replies to mail you sent get a bonus. A cheap rule layer runs first, the LLM judges the rest and
  returns validated JSON (importance 0–10, reason, action, language).
- **Voice notifications.** Choose between a repeating beep reminder, or the app asking *"Do you have time to hear your
  new mail?"*. It then reads a short summary (max 4 sentences) per mail and understands commands like *next / repeat /
  skip / stop* (PL + EN).
- **Backlog of older unread mail.** If older **unread** messages look important, the app asks separately whether you want
  to hear them. Your answer is remembered, also across restarts.
- **Topic digest — "connect the dots".** Summarises the last month by default (configurable): threads, who wrote to
  whom, why, and whether the ball is in your court or waiting on others. *(Used on live mail, including your sent mail.)*
- **Contact card and "AI mail search".** Shows the full context of a person when you are about to reply, and finds the
  likeliest mails from a plain-language description (e.g. *"that mail from Kowalski about the renovation invoice"*),
  with a reason and a confidence level. *(Covered by tests; not yet exercised much on live mail.)*
- **"Ignore…" and "VIP…" buttons** next to every important mail (desktop and phone): ignore *similar mail* (same sender
  and topic), *everything from the sender* or *the whole domain* — or the exact opposite, mark it **VIP** so such mail is
  always reported. Rules are listed (and removable) in Settings; ignored threads disappear from the digest and VIP
  threads come first. A suspicious (phishing-looking) mail can never be made VIP with one click. Optionally, everyone
  you wrote to (your Sent folder) counts as a known correspondent.
- **Friendly setup wizard**, plain-language errors, big buttons, PL/EN interface.

### Screenshots

| Setup wizard | Main window | Settings |
|---|---|---|
| ![Add account](docs/screenshots/wizard_account.png) | ![Main window](docs/screenshots/main_window.png) | ![Settings](docs/screenshots/settings.png) |

| Topic digest | Contact context | AI mail search |
|---|---|---|
| ![Digest](docs/screenshots/main_window_digest.png) | ![Context](docs/screenshots/main_window_context.png) | ![Search](docs/screenshots/search_dialog.png) |

*Screenshots are rendered offscreen with sample data.*

## Privacy and safety

- **Read-only.** The app never sends, deletes or marks mail as read (`BODY.PEEK`).
- **Local AI only.** Mail content goes only to the Ollama endpoint(s) you configure.
- **Passwords** live in the system keyring (fallback: an AES-256-GCM encrypted file with a scrypt key; optional FIDO2
  `hmac-secret` protection). They are never written to the config file or logs.
- **TLS is mandatory** for IMAP; plain connections are refused.
- **The local index stores only metadata and short summaries** (never full mail bodies), with a retention limit
  (`index_retention_days`, default 90).
- **Anti-phishing rules are non-negotiable** — see [`SECURITY.md`](SECURITY.md): the app never opens links, never
  downloads attachments and never obeys instructions found (or hidden) in mail. Implemented: safe fetch
  without attachment bodies, hidden-text stripping, untrusted-data delimiters against prompt injection, phishing
  scoring (spoofing, look-alike domains, credential lures with foreign links, brand impersonation), links defanged
  and never read aloud, and static tests forbidding link opening. The heuristics are tuned on a few real mailboxes
  only — more cases are welcome in [#9](../../issues/9).

## Status

| Area | Status |
|---|---|
| Config, SQLite de-duplication, mail parsing, rules, Ollama client with LAN/local failover, summaries | ✅ |
| IMAP fetching (read-only, TLS only), backlog of unread mail, pipeline, scheduler, service loop | ✅ (tested on fakes only) |
| Secret storage: keyring, encrypted file, FIDO2 backend | ✅ (FIDO2 on a fake device only) |
| Voice: Piper TTS, faster-whisper STT, dialog, beeper | ✅ (fakes; no real audio hardware test) |
| GUI: wizard, main window, settings, tray, PL/EN | ✅ (used live on Linux) |
| Topic digest, thread linking, contact card, AI search | ✅ (incl. sent-mail indexing) |
| Anti-phishing hardening | ✅ implemented, heuristics tuned on a few real mailboxes ([#9](../../issues/9)) |
| Android companion app (QR pairing, notifications, voice, topic digest, Ignore/VIP) | ✅ tested on a real phone |
| Live-mailbox tests: IMAP + AI + voice on Linux | ✅ partial (several mailboxes) |
| More providers (Gmail/Outlook), Windows, packaging (.exe/AppImage) | ⏳ ([#3](../../issues/3)) |

Details and architecture decisions: [`AGENTS.md`](AGENTS.md). Open work is tracked in
[Issues](../../issues) — several are good places to start.

## Omarchy / Arch Linux (primary platform)

MailVoice is built and tested on [Omarchy](https://omarchy.org) (Arch, Hyprland, Wayland). A few Arch specifics:

- **Package manager is `pacman`, not `apt`**: `sudo pacman -S <package>` (not `pacman install`). You need no system
  package for voice — Piper and `sounddevice` come from `pip`; PortAudio and PipeWire ship with Omarchy.
- **Python 3.12 via `mise`.** Arch ships the newest Python (3.14) for which some dependencies have no wheels yet.
  Omarchy includes `mise`, so use it for a project-local 3.12:
  ```bash
  mise install python@3.12
  git clone https://github.com/wasyleque/read_my_emails_omarchy.git && cd read_my_emails_omarchy
  "$(mise where python@3.12)/bin/python3.12" -m venv .venv
  source .venv/bin/activate
  pip install -e ".[voice]"
  ```
- **Ollama**: `sudo pacman -S ollama` (GPU users: `ollama-cuda`), then `ollama pull qwen3:8b`. The wizard detects it
  automatically; an Ollama on another machine in your LAN works too (enter its address under *Advanced*).
- **Passwords** go to the Omarchy keyring (`gnome-keyring` / Secret Service) — nothing to configure.
- **Run:** `python -m mailvoice` or simply `mailvoice` (inside the venv). ⚠️ Typing `python -m mail<Tab>` may
  complete to the stdlib `mailbox` module, which does nothing — type the full name `mailvoice`.
- **Launcher entry** (shows up in the Omarchy app menu):
  ```bash
  mkdir -p ~/.local/share/applications
  cat > ~/.local/share/applications/mailvoice.desktop <<EOF
  [Desktop Entry]
  Type=Application
  Name=MailVoice
  Comment=Voice assistant for your email
  Exec=$PWD/.venv/bin/python -m mailvoice
  Terminal=false
  Categories=Network;Email;
  EOF
  ```
- **Start with the session** — add to `~/.config/hypr/autostart.lua`:
  ```lua
  o.launch_on_start("/full/path/to/read_my_emails_omarchy/.venv/bin/python -m mailvoice")
  ```
- **Logs** for troubleshooting: `~/.local/state/mailvoice/log/mailvoice.log`.

## Install (for users)

> No packaged installer yet. You need Python 3.12.

1. **Ollama** — install from [ollama.com](https://ollama.com), then pull a model:
   ```bash
   ollama pull qwen3:8b                         # fast, good for English
   ollama pull qooba/bielik-11b-v3.0-instruct   # best for Polish
   ```
2. **Voice (optional)** — it is installed together with the app (step 3: `pip install -e ".[voice]"` brings
   `sounddevice`, `faster-whisper` and the `piper` speech engine; no `apt`/`pacman` package needed). Then download
   the voices once:
   ```bash
   python -m piper.download_voices --download-dir ~/.local/share/mailvoice/voices \
       pl_PL-darkman-medium en_US-lessac-medium
   ```
   If a voice is missing the app tells you the exact command. Without voice it falls back to beeps and on-screen
   messages.
3. **MailVoice**
   ```bash
   git clone https://github.com/wasyleque/read_my_emails_omarchy.git
   cd read_my_emails_omarchy
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -e ".[voice]"
   python -m mailvoice
   ```
4. A step-by-step wizard starts on first run: language → mail account (with a connection test) → Ollama detection →
   what matters to you → notifications and a voice test.

**Gmail:** you need an *app password* (Google Account → Security → 2-step verification → App passwords). The wizard
explains this. Use a test account first.

## Phone Companion App (Android)

MailVoice includes a local HTTPS/WebSocket server (`pip install -e ".[server]"`) for an Android companion app over Wi-Fi:
- **Zero raw email or attachments on the phone:** The phone only receives summaries and notifications for important mail.
- **QR code pairing:** Easily paired via Settings → *Phone (Android)* with a 120s one-time code and certificate SHA-256 pinning.
- **Headless mode:** Run the service and server without GUI windows via `mailvoice-server` or `python -m mailvoice --headless`.
- **On the phone:** important mail with summaries, the topic digest ("Matters": waiting for me / for others), voice
  control (the phone does speech-to-text and text-to-speech, analysis stays on your computer) and the same
  **Ignore… / VIP…** buttons.
- See [`docs/mobile-api.md`](docs/mobile-api.md) for full API documentation.

## Develop

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,voice]"
ruff check . && QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Code rules: business logic lives in `src/mailvoice/core/` with **no Qt dependency**; the UI in `ui/` has no business
logic; voice backends sit behind Protocols so they can be faked; every function gets a test; `ruff check .` and
`pytest` must pass before a PR. Please read [`SECURITY.md`](SECURITY.md) before touching mail handling.

## Contributing

- **Bug reports** — especially from different mail providers (folder names, encodings, `UIDVALIDITY`, OAuth quirks).
- **Windows testing** — audio, microphone, FIDO2.
- **Features and pull requests.**

⚠️ **Never paste real emails, passwords or tokens into issues.** Report security problems privately via the
repository's *Security → Report a vulnerability* page.

## License

GPL-3.0-or-later — see [`LICENSE`](LICENSE).
