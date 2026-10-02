# Specyfikacja API serwera mobilnego MailVoice (v1)

Dokumentacja techniczna lokalnego API serwera MailVoice przeznaczonego dla aplikacji mobilnej Android (np. Poco F4, Android 14) łączącej się przez Wi-Fi w sieci lokalnej.

---

## 1. Architektura i zasady bezpieczeństwa

Aplikacja mobilna pełni rolę **lekkiego klienta interfejsu i głosu**:
- **Brak połączeń wychodzących z serwera do chmury**: Serwer na PC działa wyłącznie w trybie nasłuchu na interfejsie sieci lokalnej (LAN IP). Nie używa pośredników, zewnętrznych serwerów powiadomień ani usług relay.
- **Połączenie poza domem**: Wyłącznie przez własny tunel VPN użytkownika (np. WireGuard / Tailscale / OpenVPN). Porty nie powinny być wystawiane publicznie do internetu bez ochrony tunelu.
- **Certificate Pinning (odcisk certyfikatu SHA-256)**: Serwer generuje samopodpisany certyfikat ECDSA P-256. Podczas parowania telefon otrzymuje 64-znakowy odcisk SHA-256 w kodzie QR i musi go przypiąć (pinning), odrzucając wszelkie certyfikaty o innym odcisku (odporność na ataki typu Man-in-the-Middle).
- **Bezpieczne tokeny urządzenia**: Telefon otrzymuje 32-bajtowy kryptograficznie losowy token Bearer. W bazie danych serwera przechowywany jest wyłącznie hash SHA-256 tokenu. Weryfikacja tokenu następuje w stałym czasie (`hmac.compare_digest`).
- **Ochrona prywatności i antyphishing**:
  - Serwer **nigdy nie przesyła surowej treści wiadomości e-mail** (ani w HTML, ani w tekście jawnym).
  - Serwer **nigdy nie przesyła załączników**.
  - Wszystkie adresy URL w tematach i podsumowaniach są zdefangowane (`[link pominięty]`).
  - Wiadomości oznaczone jako podejrzane (phishing / malware) mają zablokowane streszczenie — serwer zwraca wyłącznie ostrzeżenie.
  - Identyfikatory wiadomości w API (`id`) to 24-znakowe, nieprzewidywalne wartości skrótu HMAC z losowym kluczem serwera (brak ujawniania konta, folderu czy UID).

---

## 2. Format parowania przez kod QR

Podczas wywołania operacji parowania w GUI lub przez API generowany jest jednorazowy kod 6-znakowy ważny przez 120 sekund.

### Format adresu URL w kodzie QR:
```text
mailvoice://pair?host=<ip>&port=<port>&code=<kod>&fp=<sha256_certyfikatu>&v=1
```

### Parametry:
| Parametr | Typ | Opis |
| :--- | :--- | :--- |
| `host` | String | Adres IP serwera w sieci LAN (np. `192.168.1.50`) |
| `port` | Int | Numer portu HTTPS (domyślnie `8765`) |
| `code` | String | 6-znakowy jednorazowy kod autoryzacyjny (np. `K7P9X2`) |
| `fp` | String | 64-znakowy odcisk palca SHA-256 certyfikatu serwera (hex) |
| `v` | Int | Wersja protokołu (obecnie `1`) |

---

## 3. Uwierzytelnianie

Endpoint `POST /v1/pair` nie wymaga tokenu (wykorzystuje kod parowania).
Wszystkie pozostałe endpointy REST wymagają nagłówka HTTP:
```http
Authorization: Bearer <TOKEN_32_BAJTY_HEX>
```
Dla połączenia WebSocket token może zostać przekazany jako parametr w zapytaniu:
```text
wss://<ip>:<port>/v1/events?token=<TOKEN_32_BAJTY_HEX>
```
Brak tokenu, token błędny lub odwołany skutkuje kodem HTTP `401 Unauthorized`.

---

## 4. Endpointy REST

### 4.1. Parowanie urządzenia
`POST /v1/pair`
Używane raz podczas pierwszego połączenia z telefonem.

**Limit**: maksymalnie 5 prób na minutę z jednego IP (ochrona przed brute-force).

**Request Body**:
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
  "token": "a1b2c3d4e5f6... (32 bajty hex)",
  "message": "Urządzenie zostało pomyślnie sparowane."
}
```

**Błędy**:
- `400 Bad Request`: Błędny kod, brak aktywnej sesji parowania lub wygasły kod.
- `403 Forbidden`: Osiągnięto limit sparowanych urządzeń (`server.max_devices`, domyślnie 5).
- `429 Too Many Requests`: Przekroczono limit prób z danego adresu IP.

---

### 4.2. Status serwera
`GET /v1/status`

Zwraca ogólny stan aplikacji bez ujawniania danych osobowych ani adresów e-mail.

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

### 4.3. Lista ważnych wiadomości
`GET /v1/mails/important?limit=20`

Zwraca metadane i streszczenia ostatnich ważnych maili. Wszystkie odnośniki URL są usunięte lub zdefangowane.

**Parametry Query**:
- `limit`: liczba wiadomości (od 1 do 100, domyślnie 20).

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

### 4.4. Streszczenie pojedynczej wiadomości
`GET /v1/mails/{id}/summary`

Dla bezpiecznych wiadomości zwraca zdefangowane streszczenie. Dla wiadomości podejrzanych streszczenie jest ukryte, a serwer zwraca ostrzeżenie.

**Response 200 OK (bezpieczny mail)**:
```json
{
  "id": "7b8f9e12a4c5d6e7f8012345",
  "suspicious": false,
  "warning": null,
  "summary": "Przesłano zaktualizowaną ofertę handlową do końca tygodnia."
}
```

**Response 200 OK (podejrzany mail)**:
```json
{
  "id": "c1a2b3d4e5f60718293a4b5c",
  "suspicious": true,
  "warning": "Uwaga, ta wiadomość wygląda na podejrzaną. Treść nie została pobrana.",
  "summary": null
}
```

---

### 4.5. Potwierdzenie odsłuchania wiadomości (ACK)
`POST /v1/mails/{id}/ack`

Oznacza wiadomość lokalnie w bazie jako odsłuchaną/potwierdzoną przez użytkownika. **Nie modyfikuje stanu skrzynki pocztowej na serwerze IMAP**.

**Response 200 OK**:
```json
{
  "status": "ok",
  "message": "Wiadomość oznaczona jako wysłuchana."
}
```

---

### 4.6. Podsumowanie tematów (Topic Digest)
`GET /v1/digest?days=30`

Zwraca zagregowane podsumowanie tematów i wątków z ostatnich N dni.

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
      "who_to_whom": ["Kowalski -> Ty", "Ty -> Zarząd"]
    }
  ]
}
```

---

### 4.7. Przesłanie komendy głosowej
`POST /v1/voice/command`

Aplikacja mobilna wykonuje rozpoznawanie mowy lokalnie na telefonie (np. offline przez silnik Android STT) i przesyła tekst do zinterpretowania przez serwer.

**Request Body**:
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

Obsługiwane akcje (`action`):
- `next`: przejście do kolejnej wiadomości
- `repeat`: ponowne odtworzenie bieżącej wiadomości
- `skip`: pominięcie wiadomości
- `stop`: zatrzymanie odtwarzania
- `yes`: potwierdzenie pytania (np. odsłuchaj zaległe / czytaj maile)
- `no`: odroczenie pytania
- `louder`: zwiększenie głośności
- `quieter`: zmniejszenie głośności
- `digest`: prośba o podsumowanie tematów
- `contact`: zapytanie o kontekst kontaktu
- `search`: zapytanie o wyszukanie wiadomości
- `unknown`: nierozpoznana komenda

---

### 4.8. Odłączenie urządzenia
`DELETE /v1/devices/self`

Odwołuje token bieżącego urządzenia. Po wywołaniu tego endpointu token staje się trwale nieważny.

**Response 200 OK**:
```json
{
  "status": "ok",
  "message": "Urządzenie zostało pomyślnie odłączone."
}
```

---

## 5. Strumień zdarzeń w czasie rzeczywistym (WebSocket)

`GET /v1/events?token=<TOKEN>`

Ustanawia dwukierunkowe połączenie WebSocket (z automatycznym heartbeat co 25 s). Serwer przesyła powiadomienia o nowych mailach w czasie rzeczywistym.

### Przykłady zdarzeń:

#### 1. Nowe ważne maile:
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

#### 2. Wykryta wiadomość podejrzana:
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

#### 3. Przypomnienia:
```json
{
  "type": "BeepReminder",
  "timestamp": "2026-10-02T19:40:00Z",
  "data": {
    "count": 2
  }
}
```
lub
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

## 6. Kody błędów HTTP i nagłówki bezpieczeństwa

Wszystkie odpowiedzi serwera zawierają następujące nagłówki bezpieczeństwa:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'none'`
- `Strict-Transport-Security: max-age=63072000; includeSubDomains`
- `Cache-Control: no-store, no-cache, must-revalidate`
- `Server: MailVoice`

Standardowe kody błędów:
- `400 Bad Request`: Błędny format JSON lub nieprawidłowe parametry.
- `401 Unauthorized`: Brak tokenu autoryzacji lub niepoprawny token.
- `404 Not Found`: Zasób (np. mail o danym ID) nie został odnaleziony.
- `413 Payload Too Large`: Rozmiar żądania przekracza 64 KB.
- `429 Too Many Requests`: Przekroczono limit zapytań (np. przy parowaniu).
- `500 Internal Server Error`: Wewnętrzny błąd serwera (zwracany bez ujawniania stack trace ani danych technicznych).
