# Bezpieczeństwo MailVoice — zasady NIENARUSZALNE

[🇬🇧 English](SECURITY.md) · **🇵🇱 Polski**

Wymóg użytkownika: **nie wchodzimy w żadne odnośniki, nie pobieramy podejrzanych załączników i nie słuchamy
instrukcji zawartych (także ukrytych) w mailach.** Każda zmiana kodu musi te zasady zachować.

## Model zagrożeń
Treść maila jest **w całości niezaufana** (nadawca, temat, treść, nagłówki, nazwy załączników, tekst odnośników, tekst
ukryty w HTML). Atakujący może: wyłudzać dane (phishing), podsuwać złośliwe linki i załączniki, wstrzykiwać polecenia
do modelu AI (prompt injection, także ukryte: biały tekst, `display:none`, znaki zerowej szerokości, komentarze HTML)
oraz wywoływać komendy głosowe (tekst mówiony przez TTS nie może stać się komendą).

## Zasady
1. **Zero odnośników.** Aplikacja nie otwiera, nie pobiera, nie podąża za żadnym URL z maila (żadnego `http(s)`,
   obrazków zdalnych, trackingu, przekierowań, `webbrowser`, `QDesktopServices.openUrl`, `setOpenExternalLinks(True)`).
   Jedyne połączenia sieciowe: IMAP użytkownika i adresy Ollamy z konfiguracji. Linki w UI są tekstem, nigdy klikalne,
   w formie „zdefangowanej” (`hxxps://example[.]com`). Głos nie czyta adresów URL („[link pominięty]”).
2. **Zero załączników.** Nie pobieramy treści załączników — pobieramy tylko nagłówki i części `text/plain`/`text/html`
   (BODYSTRUCTURE + `BODY.PEEK[części]`, limit rozmiaru). O załącznikach znamy tylko metadane (nazwa, typ, rozmiar) i
   oceniamy ich ryzyko (rozszerzenia wykonywalne/skryptowe/makra, podwójne rozszerzenia, archiwa chronione hasłem).
3. **Treść maila to dane, nie polecenia.** Do LLM trafia wyłącznie jako wyraźnie oznaczony blok danych niezaufanych;
   prompt systemowy mówi, że żadne instrukcje z maila nie obowiązują. LLM nie ma żadnych narzędzi ani uprawnień, jego
   wyjście to ściśle walidowany JSON z wąskimi enumami (nic nie wykonuje się z jego tekstu). Wykryte próby injection
   są sygnałem PODEJRZENIA, nigdy ewentualnym wykonaniem.
4. **Pilność ≠ ważność.** Presja czasu („natychmiast”, „konto zablokowane”) w mailu o wysokim ryzyku NIE podnosi
   ważności — wręcz oznacza go jako podejrzany.
5. **Komendy głosowe tylko z mikrofonu użytkownika.** Tekst z maila nigdy nie jest interpretowany jako komenda.
6. **Tekst ukryty jest usuwany** przed analizą (HTML ukryty stylami, zerowa szerokość, mikroskopijna czcionka, biały na
   białym, komentarze), a jego obecność jest sygnałem ryzyka.
7. **Tylko odczyt**: nic nie wysyłamy, nie usuwamy, nie oznaczamy (BODY.PEEK). Wniosek: nawet przejęty model nie
   może wysłać maila ani zmienić skrzynki.
8. **Sekrety** tylko w sejfie (patrz `core/secrets.py`), treści maili i haseł nie logujemy.

## Wykrywanie phishingu (warstwa reguł, bez LLM) — wynik `risk: low|medium|high` + powody po ludzku
- Rozbieżność nazwy wyświetlanej i adresu nadawcy; podszywanie pod znane kontakty/VIP (domeny podobne:
  homoglify, punycode, odległość edycyjna); `Reply-To` na inną domenę niż `From`.
- Nagłówek `Authentication-Results`: SPF/DKIM/DMARC `fail`/`softfail`/brak.
- Linki: tekst wyświetlany ≠ rzeczywisty adres, skracacze, adresy IP, `@` w URL, nietypowe TLD, punycode.
- Prośby o dane logowania/płatność/kody (PL/EN), presja czasu, nietypowe formy płatności.
- Ryzykowne załączniki (metadane), tekst ukryty w HTML, ślady prompt injection (PL/EN: „zignoruj poprzednie
  instrukcje”, „ignore previous instructions”, „jesteś teraz…”, `system:`, itp.).
- Wiadomość o wysokim ryzyku: oznaczenie „⚠ Podejrzany”, głos: „Uwaga, ta wiadomość wygląda na podejrzaną” bez czytania
  jej treści i linków; nie podnosi ważności; powody widoczne w prosty sposób.

## Zewnętrzni dostawcy AI i wykrywanie serwera w sieci (opcjonalne, WYŁĄCZONE domyślnie)
Domyślnie treść maili trafia **wyłącznie** do lokalnego/LAN-owego Ollamy. Użytkownik może świadomie włączyć dostawcę
zewnętrznego (np. OpenAI, Anthropic, usługi zgodne z OpenAI API). Wtedy **dane opuszczają komputer** — obowiązują zasady:
1. **Świadoma zgoda:** osobny ekran po ludzku („Treść Twoich maili będzie wysyłana do firmy X. Może zawierać dane
   osobiste i poufne.”), zgoda zapisana per dostawca, możliwość cofnięcia; bez zgody żadne żądanie nie wychodzi.
2. **Minimalizacja danych:** do dostawcy zewnętrznego idzie tylko to, co konieczne (nadawca, temat, ucięty fragment
   treści już po usunięciu ukrytego tekstu, bez załączników, bez linków/URL-i, bez nagłówków uwierzytelniających);
   opcja „tylko metadane” (bez treści). Nigdy pełne treści, nigdy hasła, nigdy zawartość indeksu.
3. **Tylko HTTPS** i weryfikacja certyfikatu; klucz API wyłącznie w sejfie (`SecretStore`), nigdy w configu/logach.
4. **Maile podejrzane (ryzyko wysokie) i oznaczone jako wrażliwe nie idą do dostawcy zewnętrznego** — tylko lokalnie
   albo wcale. Konta i VIP można oznaczyć jako „tylko lokalnie”.
5. **Przejrzystość:** w UI zawsze widać, który dostawca analizuje (ikona „🌐 zewnętrzny” vs „🏠 lokalny”), licznik
   wysłanych żądań, a przy błędzie/limicie czytelny komunikat; failover z zewnętrznego na lokalny dozwolony, odwrotnie
   NIE (nigdy cicho nie „awansuj” maila do chmury).
6. **Brak ukrytych połączeń:** lista dozwolonych hostów sieciowych jest jawna w kodzie i pilnowana testem statycznym.

**Wykrywanie Ollamy w sieci** — wyłącznie na żądanie użytkownika (przycisk), nigdy w tle: skanuje tylko adresy
prywatne (RFC1918/link-local, własna podsieć /24 i znane hosty), tylko port Ollamy, krótkie timeouty, ograniczona
liczba równoległych połączeń, potwierdzenie rozpoznania odpowiedzią `/api/tags`. Nigdy nie skanuje adresów publicznych.
Użytkownik musi potwierdzić znaleziony serwer przed zapisaniem; ostrzeż, że Ollama w LAN zwykle nie ma uwierzytelniania.

## Serwer dla aplikacji mobilnej (Android)
Komputer udostępnia lokalny serwer HTTPS/WebSocket dla aplikacji telefonu. Obowiązują nienaruszalne zasady:
1. **Domyślnie wyłączony:** Serwer mobilny jest nieaktywny dopóki użytkownik świadomie nie włączy go w Ustawieniach.
2. **Tylko sieć lokalna (LAN):** Nasłuch odbywa się wyłącznie na interfejsie LAN (Wi-Fi) lub localhost. Brak połączeń wychodzących do chmury, brak pośredników relay. Dostęp spoza sieci domowej/firmowej dozwolony wyłącznie przez własny tunel VPN użytkownika (np. WireGuard, Tailscale).
3. **TLS i przypięty odcisk (Certificate Pinning):** Połączenie szyfrowane samopodpisanym certyfikatem ECDSA P-256. Podczas parowania kod QR przekazuje 64-znakowy odcisk SHA-256 certyfikatu, który aplikacja mobilna bezwzględnie weryfikuje i przypina.
4. **Jednorazowe parowanie:** Kod parowania ważny jest przez 120 sekund i unieważniany natychmiast po pierwszym użyciu. Po 5 nieudanych próbach następuje blokada sesji parowania.
5. **Kryptograficzne tokeny w bazie:** Telefon autoryzuje się 32-bajtowym losowym tokenem Bearer. W bazie danych serwera zapisywany jest wyłącznie hash SHA-256 tokenu. Weryfikacja następuje w stałym czasie (`hmac.compare_digest`).
6. **Zero surowych treści i załączników:** Telefon otrzymuje jedynie metadane i krótkie streszczenia (max 4 zdania) z usuniętymi/zdefangowanymi linkami (`[link pominięty]`). Żadna surowa treść maila ani plik załącznika nigdy nie trafia do telefonu.
7. **Izolacja wiadomości podejrzanych:** Wiadomości oznaczone jako podejrzenie phishingu/malware mają zablokowane streszczenie — telefon otrzymuje tylko ostrzeżenie i powody ryzyka.
8. **Odwoływanie urządzeń:** Użytkownik w każdej chwili może odłączyć sparowany telefon z poziomu komputera (w Ustawieniach) lub z telefonu (`DELETE /v1/devices/self`). Odwołany token jest natychmiast trwale unieważniany.

## Zgłaszanie luk
Zgłoś prywatnie przez GitHub Security Advisories (zakładka Security repozytorium). Nie umieszczaj w publicznych issues
prawdziwych maili ani danych.
