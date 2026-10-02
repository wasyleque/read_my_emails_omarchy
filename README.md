# MailVoice (read_my_emails_omarchy)

**🇬🇧 English** · [🇵🇱 Polski](README.pl.md)

> 🚧 **Work in progress.** The core logic, GUI and voice layer exist and are covered by tests, but the app has **not yet
> been run against real mailboxes**, and microphone/speaker, Windows and hardware FIDO2 keys are **untested**.
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
  whom, why, and whether the ball is in your court or waiting on others. *(Core in place; indexing of your sent mail is
  being finished — see status.)*
- **Contact card and "AI mail search".** Shows the full context of a person when you are about to reply, and finds the
  likeliest mails from a plain-language description (e.g. *"that mail from Kowalski about the renovation invoice"*),
  with a reason and a confidence level. *(Same status as above.)*
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
  downloads attachments and never obeys instructions found (or hidden) in mail. *These rules are the design contract;
  the full implementation (safe fetch without attachments, hidden-text stripping, prompt-injection defence, phishing
  scoring) is **in progress** — tracked in [#9](../../issues/9). Until it lands, treat the app as experimental.*

## Status

| Area | Status |
|---|---|
| Config, SQLite de-duplication, mail parsing, rules, Ollama client with LAN/local failover, summaries | ✅ |
| IMAP fetching (read-only, TLS only), backlog of unread mail, pipeline, scheduler, service loop | ✅ (tested on fakes only) |
| Secret storage: keyring, encrypted file, FIDO2 backend | ✅ (FIDO2 on a fake device only) |
| Voice: Piper TTS, faster-whisper STT, dialog, beeper | ✅ (fakes; no real audio hardware test) |
| GUI: wizard, main window, settings, tray, PL/EN | ✅ (offscreen only) |
| Topic digest, thread linking, contact card, AI search | ✅ core · ⏳ sent-mail indexing |
| Anti-phishing hardening | ⏳ in progress ([#9](../../issues/9)) |
| Test on real mailboxes (Gmail/Outlook/own server), Windows, packaging (.exe/AppImage) | ⏳ ([#3](../../issues/3)) |

Details and architecture decisions: [`AGENTS.md`](AGENTS.md). Open work is tracked in
[Issues](../../issues) — several are good places to start.

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
