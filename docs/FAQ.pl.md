# Najczęściej zadawane pytania

[🇬🇧 English](FAQ.md) · **🇵🇱 Polski**

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
Nadawcy z listy VIP oraz (opcjonalnie) osoby, do których piszesz, mają gwarancję powiadomienia
(poza wiadomościami z sygnałami phishingu). Jeśli ważne maile giną: dodaj nadawcę do VIP, obniż próg albo opisz w polu „co jest dla mnie ważne”, o jaką korespondencję
chodzi. Zmiana działa na nowe maile (już ocenione nie są przeliczane).

## Jak zignorować mail lub nadawcę?
Przy mailu na liście ważnych kliknij **„Ignoruj…”** (na komputerze lub w aplikacji na telefonie) i wybierz: podobne
maile od tego nadawcy, wszystkie od nadawcy albo cała domena. Możesz też dodać reguły ręcznie w Ustawieniach →
Ocenianie ważności („Ignorowane maile”). Ignorowanie ma pierwszeństwo przed VIP, a regułę można w każdej chwili usunąć.

## Jak oznaczyć nadawcę jako VIP jednym kliknięciem?
Przy mailu na liście ważnych kliknij **„VIP…”** i wybierz: podobne maile od tego nadawcy, wszystkie od nadawcy albo
cała domena. Takie maile zawsze powiadamiają, a wątki z VIP-em stoją na początku podsumowania tematów. To lustrzane
odbicie przycisku „Ignoruj…”. Regułę usuniesz w Ustawieniach → Ludzie (VIP).

## Czy w VIP mogę wpisać samą domenę?
Tak. Możesz wpisać cały adres albo samą domenę, np. `@firma.pl`.

## Czy aplikacja otwiera linki lub pobiera załączniki?
Nie, nigdy. Pobierane są tylko nagłówki i części tekstowe wiadomości, a linki w interfejsie są tylko tekstem.

## Co z phishingiem?
Maile o wysokim ryzyku są oznaczane jako podejrzane, nie są streszczane ani czytane na głos, a pilność w treści nie
podnosi ich ważności. Szczegóły: [SECURITY.md](../SECURITY.pl.md).

## Gdzie są logi?
`~/.local/state/mailvoice/log/mailvoice.log`
