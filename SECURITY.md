# MailVoice security — INVIOLABLE rules

**🇬🇧 English** · [🇵🇱 Polski](SECURITY.pl.md)

User requirement: **we never follow any link, never download suspicious attachments and never obey instructions
contained (even hidden) in mail.** Every code change must preserve these rules.

## Threat model
Mail content is **entirely untrusted** (sender, subject, body, headers, attachment names, link text, text hidden in
HTML). An attacker may: phish for data, plant malicious links and attachments, inject commands into the AI model
(prompt injection, including hidden: white text, `display:none`, zero-width characters, HTML comments) and trigger
voice commands (text spoken by TTS must never become a command).

## Rules
1. **Zero links.** The app never opens, downloads or follows any URL from mail (no `http(s)`, remote images, tracking,
   redirects, `webbrowser`, `QDesktopServices.openUrl`, `setOpenExternalLinks(True)`). The only network connections
   are the user's IMAP servers and the Ollama addresses from the configuration. Links in the UI are text, never
   clickable, in "defanged" form (`hxxps://example[.]com`). Voice never reads URLs ("[link omitted]").
2. **Zero attachments.** We do not download attachment content — only headers and `text/plain`/`text/html` parts
   (BODYSTRUCTURE + `BODY.PEEK[parts]`, size limit). About attachments we know only metadata (name, type, size) and
   assess their risk (executable/script/macro extensions, double extensions, password-protected archives).
3. **Mail content is data, not commands.** It reaches the LLM only as a clearly marked block of untrusted data; the
   system prompt says no instruction from the mail applies. The LLM has no tools or privileges; its output is strictly
   validated JSON with narrow enums (nothing is executed from its text). Detected injection attempts are a signal of
   SUSPICION, never something to carry out.
4. **Urgency ≠ importance.** Time pressure ("immediately", "account blocked") in a high-risk mail does NOT raise its
   importance — it marks it as suspicious.
5. **Voice commands only from the user's microphone.** Text from mail is never interpreted as a command.
6. **Hidden text is removed** before analysis (HTML hidden by styles, zero-width, tiny font, white-on-white,
   comments), and its presence is a risk signal.
7. **Read-only**: we send, delete and mark nothing (BODY.PEEK). Consequence: even a hijacked model cannot send mail
   or change the mailbox.
8. **Secrets** only in the secret store (see `core/secrets.py`); we never log mail content or passwords.

## Phishing detection (rule layer, no LLM) — result `risk: low|medium|high` + reasons in plain language
- Mismatch between display name and sender address; impersonation of known contacts/VIPs (look-alike domains:
  homoglyphs, punycode, edit distance); `Reply-To` pointing to a different domain than `From`.
- `Authentication-Results` header: SPF/DKIM/DMARC `fail`/`softfail`/missing.
- Links: displayed text ≠ real address, shorteners, IP addresses, `@` in the URL, unusual TLDs, punycode.
- Requests for login data/payment/codes (PL/EN), time pressure, unusual payment methods.
- Risky attachments (metadata), text hidden in HTML, prompt-injection traces (PL/EN: "ignore previous
  instructions", "you are now…", `system:`, etc.).
- High-risk message: marked "⚠ Suspicious"; voice says "Warning, this message looks suspicious" without reading its
  content or links; it does not raise importance; the reasons are shown in plain language.

## External AI providers and network server discovery (optional, OFF by default)
By default mail content goes **only** to your local/LAN Ollama. The user may knowingly enable an external provider
(e.g. OpenAI, Anthropic, OpenAI-compatible services). Then **data leaves the computer**, and these rules apply:
1. **Informed consent:** a separate plain-language screen ("The content of your mail will be sent to company X. It may
   contain personal and confidential data."), consent stored per provider and revocable; without consent no request
   leaves the machine.
2. **Data minimisation:** only what is necessary goes to an external provider (sender, subject, a truncated part of
   the body after hidden text removal, no attachments, no links/URLs, no authentication headers); a "metadata only"
   option (no body). Never full bodies, never passwords, never the contents of the index.
3. **HTTPS only** with certificate verification; the API key only in the secret store (`SecretStore`), never in the
   config or logs.
4. **Suspicious mail (high risk) and mail marked sensitive never goes to an external provider** — only locally or
   not at all. Accounts and VIPs can be marked "local only".
5. **Transparency:** the UI always shows which provider analyses ("🌐 external" vs "🏠 local" icon), a counter of
   requests sent, and a clear message on an error/limit; failover from external to local is allowed, the reverse is
   NOT (never silently "promote" mail to the cloud).
6. **No hidden connections:** the list of allowed network hosts is explicit in the code and guarded by a static test.

**Ollama discovery on the network** — only on the user's request (a button), never in the background: it scans only
private addresses (RFC1918/link-local, the own /24 subnet and known hosts), only the Ollama port, with short
timeouts and a limited number of parallel connections, confirming a hit with an `/api/tags` response. It never scans
public addresses. The user must confirm a found server before it is saved; warn that Ollama on a LAN usually has no
authentication.

## Mobile app server (Android)
The computer exposes a local HTTPS/WebSocket server for the phone app. Inviolable rules:
1. **Off by default:** the mobile server is inactive until the user deliberately enables it in Settings.
2. **Local network (LAN) only:** it listens only on the LAN (Wi-Fi) interface or localhost. No outgoing connections to
   a cloud, no relay intermediaries. Access from outside the home/company network only through the user's own VPN
   tunnel (e.g. WireGuard, Tailscale).
3. **TLS and a pinned fingerprint (certificate pinning):** the connection is encrypted with a self-signed ECDSA P-256
   certificate. During pairing the QR code carries the certificate's 64-character SHA-256 fingerprint, which the
   mobile app strictly verifies and pins.
4. **One-time pairing:** the pairing code is valid for 120 seconds and invalidated right after first use. After 5
   failed attempts the pairing session is locked.
5. **Cryptographic tokens in the database:** the phone authenticates with a random 32-byte Bearer token. The server
   database stores only the SHA-256 hash of the token. Verification is constant-time (`hmac.compare_digest`). The
   token travels only in the `Authorization` header, never in a URL (including the WebSocket).
6. **No raw content or attachments:** the phone receives only metadata and short summaries (max 4 sentences) with
   links removed/defanged (`[link omitted]`). No raw mail body or attachment file ever reaches the phone.
7. **Isolation of suspicious messages:** messages flagged as suspected phishing/malware have their summary blocked —
   the phone gets only a warning and the risk reasons.
8. **Revoking devices:** the user can disconnect a paired phone at any time from the computer (Settings) or from the
   phone (`DELETE /v1/devices/self`). A revoked token is immediately and permanently invalidated.

## Reporting vulnerabilities
Report privately through GitHub Security Advisories (the repository's Security tab). Do not put real mail or data
in public issues.
