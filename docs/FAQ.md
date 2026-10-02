# Najczęściej zadawane pytania

## Czy aplikacja coś wysyła z mojej poczty?
Nie. Skrzynki są czytane **tylko do odczytu**: aplikacja nie wysyła, nie usuwa i nie oznacza maili jako przeczytane.

## Gdzie są moje hasła?
W systemowym pęku kluczy (na Omarchy: `gnome-keyring`). Rezerwa to plik zaszyfrowany AES-256-GCM, dostępny tylko dla
Ciebie (uprawnienia 0600). Hasła nigdy nie trafiają do pliku konfiguracyjnego ani do logów.

## Czy moje dane idą do chmury?
Domyślnie nie. Analiza działa na Twoim lokalnym lub sieciowym serwerze Ollama. Modele chmurowe (nazwa zawiera `:cloud`)
są wykluczone, bo wysyłają dane poza Twój serwer.

## Dlaczego aplikacja mnie nie słyszy?
Najczęściej wejście mikrofonu jest ustawione na 0%. Sprawdź i ustaw głośność np.
`wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.5`. Gdy mikrofon nie przekazuje dźwięku, aplikacja pokaże komunikat w oknie.
Po pytaniu usłyszysz krótki sygnał — wtedy mów.

## Jak pobrać głosy?
```bash
python -m piper.download_voices --download-dir ~/.local/share/mailvoice/voices \
    pl_PL-darkman-medium en_US-lessac-medium
```

## Jak dodać Gmaila?
W Ustawieniach → Konta wybierz dostawcę „Gmail”. Gmail wymaga **hasła aplikacji**, nie zwykłego hasła do konta
(Konto Google → Bezpieczeństwo → Weryfikacja dwuetapowa → Hasła do aplikacji).

## Jak dodać O2?
Wybierz dostawcę „O2 Poczta”. Loginem jest **pełny adres e-mail**, a w ustawieniach poczty O2 musi być **włączony IMAP**.

## Dlaczego mail nie jest oznaczony jako ważny?
Ważność to ocena modelu (0–10) plus premie z reguł (VIP, słowa kluczowe, odpowiedź na Twój mail, „znany
korespondent” — ktoś, komu pisałeś). Mail trafia na listę, gdy suma osiąga próg z suwaka „Jak ostro oceniać”.
Jeśli ważne maile giną: dodaj nadawcę do VIP, obniż próg albo opisz w polu „co jest dla mnie ważne”, o jaką korespondencję
chodzi. Zmiana działa na nowe maile (już ocenione nie są przeliczane).

## Czy w VIP mogę wpisać samą domenę?
Tak. Możesz wpisać cały adres albo samą domenę, np. `@firma.pl`.

## Czy aplikacja otwiera linki lub pobiera załączniki?
Nie, nigdy. Pobierane są tylko nagłówki i części tekstowe wiadomości, a linki w interfejsie są tylko tekstem.

## Co z phishingiem?
Maile o wysokim ryzyku są oznaczane jako podejrzane, nie są streszczane ani czytane na głos, a pilność w treści nie
podnosi ich ważności. Szczegóły: [SECURITY.md](../SECURITY.md).

## Gdzie są logi?
`~/.local/state/mailvoice/log/mailvoice.log`

---

# Frequently asked questions

## Does the app send anything from my mailbox?
No. Mailboxes are accessed **read-only**: the app never sends, deletes or marks mail as read.

## Where are my passwords stored?
In the system keyring (`gnome-keyring` on Omarchy). The fallback is an AES-256-GCM encrypted file readable only by you
(permissions 0600). Passwords never go into the config file or logs.

## Does my data go to the cloud?
Not by default. Analysis runs on your own local or LAN Ollama server. Cloud models (names containing `:cloud`) are
excluded because they send data outside your server.

## Why can't the app hear me?
Most often the microphone input volume is 0%. Set it, e.g. `wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.5`. If the
microphone delivers no sound, the app shows a message in its window. After a question you hear a short beep — speak then.

## How do I download the voices?
```bash
python -m piper.download_voices --download-dir ~/.local/share/mailvoice/voices \
    pl_PL-darkman-medium en_US-lessac-medium
```

## How do I add Gmail?
In Settings → Accounts choose the “Gmail” provider. Gmail requires an **app password**, not your regular account
password (Google Account → Security → 2-step verification → App passwords).

## How do I add O2?
Choose the “O2 Poczta” provider. The login is the **full email address**, and **IMAP must be enabled** in your O2 mail
settings.

## Why isn't a mail marked as important?
Importance is the model's score (0–10) plus bonuses from rules (VIP, keywords, replies to your mail, “known
correspondent” — someone you have written to). A mail is listed when the sum reaches the threshold set by the
“How strict” slider. If important mail gets missed: add the sender to VIP, lower the threshold, or describe in the
“what matters to me” field which correspondence is important. Changes apply to new mail (already-scored mail is not
re-scored).

## Can I put just a domain in VIP?
Yes. Enter a full address or just a domain, e.g. `@company.com`.

## Does the app open links or download attachments?
Never. Only headers and text parts of a message are fetched, and links in the UI are plain text.

## What about phishing?
High-risk mail is marked suspicious, is not summarised or read aloud, and urgency in the text does not raise its
importance. Details: [SECURITY.md](../SECURITY.md).

## Where are the logs?
`~/.local/state/mailvoice/log/mailvoice.log`
