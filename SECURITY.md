# Bezpieczeństwo MailVoice — zasady NIENARUSZALNE

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

## Zgłaszanie luk
Zgłoś prywatnie przez GitHub Security Advisories (zakładka Security repozytorium). Nie umieszczaj w publicznych issues
prawdziwych maili ani danych.
