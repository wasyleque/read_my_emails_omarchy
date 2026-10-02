# Contributing to MailVoice

MailVoice (GPL-3.0-or-later) fetches mail from several IMAP accounts **read-only**, uses a local AI model
(Ollama) to judge what matters, and tells you by voice in Polish or English.
[Wersja polska](CONTRIBUTING.pl.md)

## Getting started
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,voice]"
ruff check . && QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m mailvoice
```
On Omarchy/Arch see the *Omarchy* section of the [README](README.md) (Python 3.12 via `mise`, `pacman`, not `apt`).
Good places to start: issues labelled **good first issue**, tests with other mail providers (folder names,
encodings, `UIDVALIDITY`), and **Windows testing** (audio, microphone, FIDO2).

## Code structure
- `src/mailvoice/core/` — logic with **no Qt dependency** (fully testable)
- `src/mailvoice/voice/` — speech input/output behind `Protocol` interfaces (so they can be faked)
- `src/mailvoice/ui/` — PySide6 only, **no business logic**
- `tests/` — pytest

## Code rules
- Every function in `core/` has a test; bug fixes come with a regression test.
- Before a PR: `ruff check .` and `QT_QPA_PLATFORM=offscreen python -m pytest -q` must pass.
- Identifiers in English; comments in Polish or English.
- No hard-coded colors in the UI — use `ui/theme.py`. UI text goes through `tr()` in `ui/i18n.py` in **both** PL and EN.

## Security and privacy
Read [SECURITY.md](SECURITY.md) before touching mail handling. Non-negotiable: never open links from mail, never
download attachments, never act on instructions found in a message, read-only mailbox access, passwords only in the
secret store.
**Never paste real emails, passwords, tokens or private addresses into issues or PRs.** Report vulnerabilities
privately via *Security → Report a vulnerability*.

## Reporting bugs and opening PRs
Use the issue templates; include steps to reproduce, your environment and the error trace from
`~/.local/state/mailvoice/log/mailvoice.log` (with addresses removed). PRs: describe what and why, keep them focused,
and make sure the checks above pass.
