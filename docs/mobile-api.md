# MailVoice mobile server API specification (v1)

**🇬🇧 English** · [🇵🇱 Polski](mobile-api.pl.md)

Technical documentation of the local MailVoice server API intended for the Android mobile app (e.g. Poco F4,
Android 14) connecting over Wi-Fi on the local network.

Note: error messages in JSON responses (`error`, `message`, `warning`, `reply_text`) are returned in Polish; clients
should rely on HTTP status codes and the documented fields, not on the message text.

---

## 1. Architecture and security principles

The mobile app is a **thin interface and voice client**:
- **No outgoing connections from the server to the cloud**: the PC server only listens on the local network
  interface (LAN IP). No intermediaries, external notification servers or relay services.
- **Access away from home**: only through the user's own VPN tunnel (e.g. WireGuard / Tailscale / OpenVPN). Ports
  must not be exposed to the internet without tunnel protection.
- **Certificate pinning (SHA-256 fingerprint)**: the server generates a self-signed ECDSA P-256 certificate. During
  pairing the phone receives the 64-character SHA-256 fingerprint in the QR code and must pin it, rejecting any
  certificate with a different fingerprint (resistance to man-in-the-middle attacks).
- **Secure device tokens**: the phone receives a 32-byte cryptographically random Bearer token. The server database
  stores only the SHA-256 hash of the token. Verification is constant-time (`hmac.compare_digest`).
- **Privacy and anti-phishing**:
  - The server **never sends the raw body of an e-mail** (neither HTML nor plain text).
  - The server **never sends attachments**.
  - All URLs in subjects and summaries are defanged (`[link pominięty]`, i.e. "link omitted").
  - Messages flagged as suspicious (phishing / malware) have their summary blocked — the server returns only a
    warning.
  - Message identifiers in the API (`id`) are 24-character, unpredictable HMAC digests with a random server key (no
    disclosure of the account, folder or UID).

---

## 2. QR pairing format

When pairing is started in the GUI or through the API, a one-time 6-character code valid for 120 seconds is
generated.

### URL format in the QR code
```text
mailvoice://pair?host=<ip>&port=<port>&code=<code>&fp=<certificate_sha256>&v=1
```

### Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `host` | String | Server IP address on the LAN (e.g. `192.168.1.50`) |
| `port` | Int | HTTPS port (default `8765`) |
| `code` | String | 6-character one-time authorisation code (e.g. `K7P9X2`) |
| `fp` | String | 64-character SHA-256 fingerprint of the server certificate (hex) |
| `v` | Int | Protocol version (currently `1`) |

---

## 3. Authentication

The `POST /v1/pair` endpoint needs no token (it uses the pairing code).
All other REST endpoints require the HTTP header:
```http
Authorization: Bearer <TOKEN_32_BYTES_HEX>
```
This also applies to the WebSocket (`/v1/events`): the token goes **only in the header** `Authorization`. Passing it
in the URL (`?token=`) is rejected (`401`) because URLs end up in logs, history and intermediary servers.
A missing, wrong or revoked token results in HTTP `401 Unauthorized`.

---

## 4. REST endpoints

### 4.1. Device pairing
`POST /v1/pair`
Used once, on the first connection of a phone.

**Limit**: at most 5 attempts per minute from one IP (brute-force protection).

**Request body**:
```json
{
  "code": "K7P9X2",
  "device_name": "Poco F4"
}
```

**Response 200 OK**:
```json
{
  "status": "ok",
  "device_id": "3f8e0a1b...",
  "token": "a1b2c3d4e5f6... (32 bytes hex)",
  "message": "Urządzenie zostało pomyślnie sparowane."
}
```

**Errors**:
- `400 Bad Request`: wrong code, no active pairing session or expired code.
- `403 Forbidden`: the paired-device limit was reached (`server.max_devices`, default 5).
- `429 Too Many Requests`: the attempt limit for this IP address was exceeded.

---

### 4.2. Server status
`GET /v1/status`

Returns the general state of the application without revealing personal data or e-mail addresses.

**Response 200 OK**:
```json
{
  "version": "0.1.0",
  "last_tick": "2026-10-02T19:30:00Z",
  "accounts_count": 2,
  "active_devices_count": 1
}
```

---

### 4.3. List of important messages
`GET /v1/mails/important?limit=20`

Returns metadata and summaries of the latest important mails. All URLs are removed or defanged.
Mail matching the user's "Ignore" rules is not returned.

**Query parameters**:
- `limit`: number of messages (1 to 100, default 20).

**Response 200 OK**:
```json
{
  "mails": [
    {
      "id": "7b8f9e12a4c5d6e7f8012345",
      "sender": "Jan Kowalski <jan@firma.pl>",
      "subject": "Oferta współpracy [link pominięty]",
      "importance": 9,
      "why": "Ważna oferta od stałego kontrahenta",
      "summary": "Przesłano zaktualizowaną ofertę handlową do końca tygodnia.",
      "suspicious": false,
      "date": "2026-10-02T18:45:00Z",
      "acknowledged": false
    },
    {
      "id": "c1a2b3d4e5f60718293a4b5c",
      "sender": "Bank <bezpieczny@fake-alert.com>",
      "subject": "Twoje konto zostało zawieszone",
      "importance": 8,
      "why": "Presja czasu i wykryte cechy phishingu",
      "summary": null,
      "suspicious": true,
      "date": "2026-10-02T17:10:00Z",
      "acknowledged": false
    }
  ]
}
```

---

### 4.4. Summary of a single message
`GET /v1/mails/{id}/summary`

For safe messages returns a defanged summary. For suspicious messages the summary is hidden and the server returns a
warning.

**Response 200 OK (safe mail)**:
```json
{
  "id": "7b8f9e12a4c5d6e7f8012345",
  "suspicious": false,
  "warning": null,
  "summary": "Przesłano zaktualizowaną ofertę handlową do końca tygodnia."
}
```

**Response 200 OK (suspicious mail)**:
```json
{
  "id": "c1a2b3d4e5f60718293a4b5c",
  "suspicious": true,
  "warning": "Uwaga, ta wiadomość wygląda na podejrzaną. Treść nie została pobrana.",
  "summary": null
}
```

---

### 4.5. Acknowledging a message as heard (ACK)
`POST /v1/mails/{id}/ack`

Marks the message locally in the database as heard/acknowledged by the user. It **does not change the state of the
mailbox on the IMAP server**.

**Response 200 OK**:
```json
{
  "status": "ok",
  "message": "Wiadomość oznaczona jako wysłuchana."
}
```

---

### 4.6. Topic digest
`GET /v1/digest?days=30`

Returns an aggregated summary of topics and threads from the last N days.

Optional parameters: `limit` (1–200, default 60) — the maximum number of topics **in each status group separately**
(a small `oczekuje_na_innych` group is not pushed out by a large `oczekuje_na_mnie` one); `all=1` — also includes
the "closed" and "informational" topics (by default only their counts appear in `counts`).

**Response 200 OK**:
```json
{
  "period": "ostatnie 30 dni",
  "topics": [
    {
      "title": "Projekt wdrożenia systemu ERP",
      "status": "oczekuje_na_mnie",
      "why": "Czeka na akceptację kosztorysu",
      "importance": 9,
      "mail_count": 7,
      "last_activity": "2026-10-02T16:20:00Z",
      "who_to_whom": ["Kowalski -> Ty", "Ty -> Zarząd"],
      "vip": false
    }
  ],
  "counts": {"oczekuje_na_mnie": 134, "oczekuje_na_innych": 36, "informacyjne": 165, "zamknięte": 132},
  "total": 467,
  "shown": 60
}
```

- `status`: `oczekuje_na_mnie` (waiting for me) | `oczekuje_na_innych` (waiting for others) | `informacyjne`
  (informational) | `zamknięte` (closed).
- `vip` (optional, absent = `false`): the thread matches a user VIP rule; such threads come first in their group.
- `counts`, `total`, `shown`: the number of all topics by status, in total, and actually returned. Older server
  versions may not send these fields — a client should tolerate that.
- The first call may take a few seconds (analysis happens on the computer); further calls within about 2 minutes are
  served from a cache.

---

### 4.6a. Ignoring a message
`POST /v1/mails/{id}/ignore`

Creates an "ignore" rule on the computer based on the given message. The computer stores it in its settings (the
user can remove it there); ignored mail disappears from the important list and from the topic digest.

**Request body**:
```json
{ "mode": "similar" }
```
`mode` (default `similar`):
- `similar` — similar mail from this sender (same base subject),
- `sender` — all mail from this sender,
- `domain` — all mail from this domain (the whole organisation).

**Response 200 OK**:
```json
{ "status": "ok", "mode": "similar", "rule": "od: info@sklep.pl, temat zawiera: newsletter tygodniowy" }
```

**Errors**: `400` (unknown mode / bad JSON), `404` (unknown message), `503` (feature unavailable on the computer).
Ignoring is allowed for suspicious messages too (the recommended reaction to phishing).

---

### 4.6b. Marking VIP
`POST /v1/mails/{id}/vip`

The mirror image of ignoring: creates a VIP rule. Such mail always notifies, and threads with it come first in the
topic digest. Ignoring takes priority over VIP; adding a VIP rule removes an identical ignore rule.

Request and response as in 4.6a (modes `similar` / `sender` / `domain`).

**Errors**: as in 4.6a, plus `403` — the message is suspicious (phishing); a forged sender cannot become a VIP.

---

### 4.7. Submitting a voice command
`POST /v1/voice/command`

The mobile app performs speech recognition locally on the phone (e.g. offline through the Android STT engine) and
sends the text to the server to be interpreted.

**Request body**:
```json
{
  "text": "następny mail",
  "lang": "pl"
}
```

**Response 200 OK**:
```json
{
  "action": "next",
  "reply_text": "Przechodzę do kolejnej wiadomości."
}
```

Supported actions (`action`):
- `next`: go to the next message
- `repeat`: replay the current message
- `skip`: skip the message
- `stop`: stop playback
- `yes`: confirm a question (e.g. hear the backlog / read the mail)
- `no`: postpone the question
- `louder`: increase the volume
- `quieter`: decrease the volume
- `digest`: ask for the topic digest
- `contact`: ask for a contact's context
- `search`: ask to search for a message
- `unknown`: unrecognised command

---

### 4.8. Disconnecting a device
`DELETE /v1/devices/self`

Revokes the current device's token. After this call the token is permanently invalid.

**Response 200 OK**:
```json
{
  "status": "ok",
  "message": "Urządzenie zostało pomyślnie odłączone."
}
```

---

## 5. Real-time event stream (WebSocket)

`GET /v1/events` (header `Authorization: Bearer <TOKEN>`)

Opens a two-way WebSocket connection (with an automatic heartbeat every 25 s). The server pushes notifications about
new mail in real time.

### Event examples

#### 1. New important mail
```json
{
  "type": "NewImportant",
  "timestamp": "2026-10-02T19:35:00Z",
  "data": {
    "mails": [
      {
        "id": "7b8f9e12a4c5d6e7f8012345",
        "sender": "Klient <klient@firma.pl>",
        "subject": "Pilne zamówienie",
        "importance": 9,
        "why": "Zamówienie z krótkim terminem",
        "date": "2026-10-02T19:34:50Z",
        "suspicious": false
      }
    ]
  }
}
```

#### 2. Suspicious message detected
```json
{
  "type": "SuspiciousMail",
  "timestamp": "2026-10-02T19:35:10Z",
  "data": {
    "mail": {
      "id": "c1a2b3d4e5f60718293a4b5c",
      "sender": "Spoof <alert@phish.net>",
      "subject": "Pilna weryfikacja hasła",
      "importance": 8,
      "why": "Wykryto cechy phishingu",
      "date": "2026-10-02T19:35:05Z",
      "suspicious": true,
      "reasons": ["SPF fail", "Niezgodna domena From"]
    }
  }
}
```

#### 3. Reminders
```json
{
  "type": "BeepReminder",
  "timestamp": "2026-10-02T19:40:00Z",
  "data": {
    "count": 2
  }
}
```
or
```json
{
  "type": "AskReminder",
  "timestamp": "2026-10-02T19:45:00Z",
  "data": {
    "count": 2
  }
}
```

---

## 6. HTTP error codes and security headers

All server responses carry the following security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'none'`
- `Strict-Transport-Security: max-age=63072000; includeSubDomains`
- `Cache-Control: no-store, no-cache, must-revalidate`
- `Server: MailVoice`

Standard error codes:
- `400 Bad Request`: invalid JSON format or invalid parameters.
- `401 Unauthorized`: missing authorisation token or an incorrect token.
- `403 Forbidden`: operation refused (e.g. the device limit, or marking a suspicious message as VIP).
- `404 Not Found`: the resource (e.g. a mail with the given ID) was not found.
- `413 Payload Too Large`: the request size exceeds 64 KB.
- `429 Too Many Requests`: the request limit was exceeded (e.g. during pairing).
- `500 Internal Server Error`: an internal server error (returned without revealing a stack trace or technical
  details).
