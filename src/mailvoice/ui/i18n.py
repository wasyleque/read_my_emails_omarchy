"""Prosty moduł internacjonalizacji (i18n) bez zależności od Qt Linguist."""

from typing import Any

# Słownik tłumaczeń dla języków polskiego (pl) i angielskiego (en)
_TRANSLATIONS: dict[str, dict[str, str]] = {
    "pl": {
        # Kreator
        "wizard_title": "Kreator konfiguracji MailVoice",
        "step1_title": "Witaj w MailVoice",
        "step1_intro": (
            "Twój inteligentny asystent poczty, który przeczyta najważniejsze wiadomości na głos."
        ),
        "step1_lang_label": "Wybierz język interfejsu i asystenta:",
        "step2_title": "Dodaj konto pocztowe",
        "step2_provider": "Dostawca poczty:",
        "step2_email": "Adres e-mail:",
        "step2_password": "Hasło (zostanie bezpiecznie zaszyfrowane):",
        "step2_test_btn": "Sprawdź połączenie",
        "step2_test_testing": "Łączenie z serwerem...",
        "step2_test_ok": "Połączenie udane! Skrzynka działa poprawnie.",
        "step2_advanced": "Zaawansowane (serwer, port)",
        "step2_host": "Serwer IMAP:",
        "step2_port": "Port IMAP:",
        "step3_title": "Sztuczna inteligencja (Ollama)",
        "step3_desc": "Lokalna sztuczna inteligencja ocenia ważność maili na Twoim komputerze.",
        "step3_detected": "Wykryto działającą usługę Ollama!",
        "step3_not_detected": "Nie wykryto uruchomionego programu Ollama.",
        "step3_install_guide": (
            "Pobierz Ollama z https://ollama.com i uruchom polecenie: ollama run qwen3:8b"
        ),
        "step3_model_label": "Wybrany model AI:",
        "step3_advanced_url": "Zaawansowane (adres Ollama)",
        "step4_title": "Co jest dla Ciebie ważne?",
        "step4_templates_label": "Wybierz gotowy szablon:",
        "template_work": "Praca",
        "template_work_text": (
            "Ważne są maile od klientów, przełożonych, pilne zlecenia, terminy "
            "projektowe i faktury. Reklamy, newslettery i automatyczne powiadomienia ignoruj."
        ),
        "template_home": "Dom",
        "template_home_text": (
            "Ważne są wiadomości od rodziny, przyjaciół, informacje o rachunkach, przesyłkach "
            "kurierskich i lekarzu. Oferty i spam pomijaj."
        ),
        "template_business": "Firma",
        "template_business_text": (
            "Priorytet mają zamówienia od klientów, kwestie płatności, umowy, zapytania ofertowe "
            "i awarie systemów."
        ),
        "step4_desc_label": "Opis własnymi słowami:",
        "step4_threshold_label": "Jak ostro oceniać wiadomości?",
        "threshold_mild": "Łagodnie (przepuszczaj więcej)",
        "threshold_balanced": "Zrównoważenie (domyślnie)",
        "threshold_strict": "Tylko najważniejsze",
        "step4_vip_label": "Ważni nadawcy (VIP) — zawsze powiadamiaj:",
        "vip_hint": (
            "Wpisz cały adres albo samą domenę, np. @firma.pl — wtedy liczą się wszyscy z firmy."
        ),
        "step4_keywords_label": "Ważne słowa kluczowe w treści lub temacie:",
        "add_btn": "Dodaj",
        "remove_btn": "Usuń",
        "step5_title": "Głos i powiadomienia",
        "step5_interval_label": "Jak często sprawdzać pocztę?",
        "minutes_5": "Co 5 minut",
        "minutes_10": "Co 10 minut",
        "minutes_15": "Co 15 minut",
        "minutes_30": "Co 30 minut",
        "step5_mode_label": "Sposób powiadamiania o nowych ważnych mailach:",
        "mode_ask": "Zapytaj głosem: „Masz ważne maile, czy masz czas posłuchać?”",
        "mode_beep": "Dyskretny sygnał dźwiękowy (beep)",
        "step5_test_voice_btn": "Sprawdź głos (posłuchaj próbki)",
        "step5_voice_sample_text": "Dzień dobry. Asystent pocztowy MailVoice działa poprawnie.",
        "step6_title": "Wszystko gotowe!",
        "step6_desc": (
            "Aplikacja została skonfigurowana. Kliknij „Zakończ”, aby rozpocząć pracę asystenta."
        ),
        "btn_next": "Dalej >",
        "btn_back": "< Wstecz",
        "btn_finish": "Zakończ",
        "btn_cancel": "Anuluj",
        # Okno główne
        "app_title": "MailVoice",
        "status_ready": "Wszystko działa poprawnie",
        "status_checking": "Sprawdzam nową pocztę...",
        "status_no_accounts": (
            "Brak skonfigurowanych skrzynek pocztowych. Dodaj pierwsze konto w Ustawieniach."
        ),
        "status_last_check": "Ostatnie sprawdzenie:",
        "status_never": "brak danych",
        "btn_check_now": "Sprawdź teraz",
        "btn_mute": "Wycisz przypomnienia",
        "btn_unmute": "Wyłącz wyciszenie",
        "btn_settings": "Ustawienia",
        "section_important": "Ostatnie ważne wiadomości",
        "btn_listen_summary": "Posłuchaj streszczenia",
        "col_account": "Konto",
        "col_sender": "Od",
        "col_subject": "Temat",
        "col_reason": "Dlaczego ważny?",
        "col_actions": "Akcja",
        "no_important_emails": "Brak nowych ważnych maili. Wszystko pod kontrolą!",
        "backlog_dialog_title": "Zaległe nieprzeczytane wiadomości",
        "backlog_dialog_msg": (
            "Masz {count} starszych nieprzeczytanych ważnych wiadomości. Czy chcesz ich wysłuchać?"
        ),
        "btn_yes": "Tak, posłuchaj",
        "btn_no": "Nie, pomiń",
        "tray_tooltip": "MailVoice — Asystent pocztowy",
        "tray_show": "Pokaż okno",
        "tray_exit": "Zakończ program",
        # Ustawienia
        "settings_title": "Ustawienia MailVoice",
        "tab_account": "Konta pocztowe",
        "accounts_list_title": "Skonfigurowane konta:",
        "btn_add_account": "Dodaj konto",
        "btn_remove_account": "Usuń konto",
        "remove_account_title": "Usuń konto",
        "remove_account_confirm": (
            "Czy na pewno chcesz usunąć konto '{account}'? "
            "Spowoduje to także usunięcie zapisanego hasła."
        ),
        "account_details_title": "Szczegóły wybranego konta",
        "acc_status_pwd_saved": "hasło zapisane",
        "acc_status_no_pwd": "brak hasła",
        "new_account_label": "Nowe konto",
        "account_empty_email_error": "Każde konto musi mieć wpisany adres e-mail.",
        "account_invalid_port_error": (
            "Numer portu dla konta '{account}' musi być liczbą od 1 do 65535."
        ),
        "account_ssl_required_error": "Konto '{account}' wymaga bezpiecznego połączenia SSL / TLS.",
        "account_duplicate_error": (
            "To konto już jest na liście: '{account}'. Adresy kont muszą być unikalne."
        ),
        "account_no_account_selected": "Wybierz konto z listy lub kliknij Dodaj konto.",
        "step2_multi_hint": (
            "Wskazówka: kolejne skrzynki pocztowe możesz dodać w dowolnym momencie w Ustawieniach."
        ),
        "step2_sent_folder": "Folder Wysłane:",
        "tab_analysis": "Ocenianie ważności",
        "tab_notifications": "Głos i powiadomienia",
        "tab_ollama": "Model AI (Ollama)",
        "ollama_detect_btn": "Wykryj modele",
        "ollama_detecting": "Szukam serwera Ollama i pobieram listę modeli...",
        "ollama_detected_server": "Znaleziono serwer ({source}) — {count} modeli",
        "ollama_source_local": "ten komputer",
        "ollama_source_lan": "sieć lokalna",
        "ollama_not_detected": "Nie znaleziono działającego serwera Ollama.",
        "ollama_install_guide": (
            "Zainstaluj i uruchom Ollamę ze strony https://ollama.com. "
            "W razie potrzeby podaj adres serwera w Zaawansowanych poniżej."
        ),
        "ollama_general_model_label": "Model do analizy poczty:",
        "ollama_polish_model_label": "Model do języka polskiego:",
        "ollama_same_as_general": "taki sam jak ogólny",
        "ollama_recommended_tag": " (zalecany)",
        "ollama_recommended_pl_tag": " (zalecany do PL)",
        "ollama_show_all_models": "Pokaż wszystkie modele",
        "ollama_cloud_excluded_hint": (
            "Modele chmurowe (:cloud) są wykluczone, ponieważ przesyłają dane poza Twój serwer."
        ),
        "ollama_model_missing_tag": "niezainstalowany",
        "ollama_model_missing_warn": (
            "⚠ Wybrany model nie jest zainstalowany na serwerze Ollama. "
            "Analiza maili może zakończyć się błędem."
        ),
        "ollama_model_missing_confirm": (
            "Wybrany model '{model}' nie jest zainstalowany na serwerze Ollama. "
            "Czy na pewno chcesz zapisać tę konfigurację?"
        ),
        "ollama_check_btn": "Sprawdź model",
        "ollama_checking": "Wysyłam zapytanie testowe do modelu...",
        "btn_save": "Zapisz zmiany",
        "btn_close": "Zamknij",
        "save_success": "Ustawienia zostały pomyślnie zapisane.",
        # Podsumowanie tematów (Digest)
        "tab_messages": "Wiadomości",
        "tab_digest": "Podsumowanie tematów",
        "digest_timeframe_label": "Okres:",
        "digest_period_week": "Ostatni tydzień (7 dni)",
        "digest_period_month": "Ostatni miesiąc (30 dni)",
        "digest_period_quarter": "Ostatnie 3 miesiące (90 dni)",
        "btn_refresh_digest": "Odśwież podsumowanie",
        "digest_group_waiting_me": "Czeka na Ciebie",
        "digest_group_waiting_others": "Czeka na innych",
        "digest_group_info": "Informacje i zakończone",
        "digest_empty": "Brak tematów w wybranym okresie.",
        "digest_no_topics_in_group": "Brak spraw w tej grupie.",
        "digest_btn_listen": "Posłuchaj",
        "digest_who_to_whom": "Kto → Do kogo",
        "digest_status_loading": "Przygotowywanie podsumowania...",
        "settings_digest_days_label": "Domyślny okres podsumowania tematów (dni):",
        "step4_digest_days_label": "Okres podsumowania tematów (dni):",
        # Kontekst kontaktu i wyszukiwanie AI
        "context_panel_title": "Kontekst nadawcy",
        "context_select_mail": "Wybierz wiadomość z listy, aby zobaczyć kontekst nadawcy.",
        "context_loading": "Wczytywanie kontekstu...",
        "context_unknown_sender": ("Nie znam jeszcze tego nadawcy w Twojej historii kontaktów."),
        "context_relationship": "Kim jest:",
        "context_open_items": "Otwarte sprawy:",
        "context_last_exchange": "Ostatnia wymiana:",
        "context_no_open_items": "Brak otwartych spraw.",
        "btn_search_ai": "Wyszukaj maila (AI)",
        "search_dialog_title": "Wyszukiwanie wiadomości (AI)",
        "search_input_label": "Opisz, czego szukasz:",
        "search_input_placeholder": "np. ten mail od Kowalskiego o fakturze za remont...",
        "search_period_label": "Okres przeszukiwania:",
        "search_period_30": "Ostatnie 30 dni",
        "search_period_90": "Ostatnie 90 dni",
        "search_period_365": "Ostatni rok (365 dni)",
        "btn_run_search": "Szukaj",
        "search_status_searching": "Wyszukiwanie i analiza wiadomości przez AI...",
        "search_no_results": (
            "Nie znaleziono pasujących wiadomości. Spróbuj poszerzyć okres lub zmienić zapytanie."
        ),
        "search_confidence_high": "Wysoka pewność",
        "search_confidence_medium": "Średnia pewność",
        "search_confidence_low": "Niska pewność",
        "search_why_probable": "Dlaczego prawdopodobny:",
        "badge_suspicious": "⚠ Podejrzany",
        "suspicious_warning_dialog": (
            "Ta wiadomość została oznaczona jako potencjalnie niebezpieczna "
            "(phishing / złośliwe oprogramowanie). "
            "Nie otwieraj odnośników ani nie pobieraj załączników."
        ),
        "suspicious_reasons_title": "Powody oznaczenia jako podejrzany:",
        "error_generic_title": "Coś poszło nie tak",
        "error_generic_msg": (
            "Coś poszło nie tak. Spróbuj ponownie. Jeśli problem wraca, kliknij Szczegóły."
        ),
        "btn_details": "Szczegóły techniczne",
        "btn_hide_details": "Ukryj szczegóły",
    },
    "en": {
        # Wizard
        "wizard_title": "MailVoice Setup Wizard",
        "step1_title": "Welcome to MailVoice",
        "step1_intro": (
            "Your smart email assistant that speaks your most important messages out loud."
        ),
        "step1_lang_label": "Select interface and voice language:",
        "step2_title": "Add Email Account",
        "step2_provider": "Email provider:",
        "step2_email": "Email address:",
        "step2_password": "Password (stored securely):",
        "step2_test_btn": "Test Connection",
        "step2_test_testing": "Connecting to server...",
        "step2_test_ok": "Connection successful! Mailbox works correctly.",
        "step2_advanced": "Advanced (server, port)",
        "step2_host": "IMAP Server:",
        "step2_port": "IMAP Port:",
        "step3_title": "Artificial Intelligence (Ollama)",
        "step3_desc": (
            "Local artificial intelligence evaluates message importance right on your computer."
        ),
        "step3_detected": "Ollama service detected and running!",
        "step3_not_detected": "Ollama service was not detected.",
        "step3_install_guide": (
            "Download Ollama from https://ollama.com and run: ollama run qwen3:8b"
        ),
        "step3_model_label": "Selected AI model:",
        "step3_advanced_url": "Advanced (Ollama URL)",
        "step4_title": "What is important to you?",
        "step4_templates_label": "Choose a template:",
        "template_work": "Work",
        "template_work_text": (
            "Important: emails from clients, managers, urgent tasks, project deadlines "
            "and invoices. Ignore newsletters, ads, and automated notifications."
        ),
        "template_home": "Personal",
        "template_home_text": (
            "Important: messages from family and friends, utility bills, parcel deliveries "
            "and doctor visits. Skip promotional offers and spam."
        ),
        "template_business": "Business",
        "template_business_text": (
            "Priority given to client orders, payment issues, contracts, inquiries, "
            "and server or system outages."
        ),
        "step4_desc_label": "Description in your own words:",
        "step4_threshold_label": "How strictly to evaluate messages?",
        "threshold_mild": "Mild (allow more through)",
        "threshold_balanced": "Balanced (default)",
        "threshold_strict": "Strict (critical only)",
        "step4_vip_label": "Important senders (VIP) — always notify:",
        "vip_hint": (
            "Enter a full address or just a domain, e.g. @company.com — everyone there counts."
        ),
        "step4_keywords_label": "Important keywords in subject or body:",
        "add_btn": "Add",
        "remove_btn": "Remove",
        "step5_title": "Voice and Notifications",
        "step5_interval_label": "How often to check for mail?",
        "minutes_5": "Every 5 minutes",
        "minutes_10": "Every 10 minutes",
        "minutes_15": "Every 15 minutes",
        "minutes_30": "Every 30 minutes",
        "step5_mode_label": "Notification mode for new important mail:",
        "mode_ask": "Voice prompt: 'You have important mail, do you have time to listen?'",
        "mode_beep": "Discreet audio beep",
        "step5_test_voice_btn": "Test Voice (listen to sample)",
        "step5_voice_sample_text": "Hello. MailVoice email assistant is working properly.",
        "step6_title": "All Done!",
        "step6_desc": "Application is now configured. Click 'Finish' to launch the assistant.",
        "btn_next": "Next >",
        "btn_back": "< Back",
        "btn_finish": "Finish",
        "btn_cancel": "Cancel",
        # Main window
        "app_title": "MailVoice",
        "status_ready": "All systems operational",
        "status_checking": "Checking for new mail...",
        "status_no_accounts": "No mailboxes configured. Add your first account in Settings.",
        "status_last_check": "Last check:",
        "status_never": "none",
        "btn_check_now": "Check Now",
        "btn_mute": "Mute Reminders",
        "btn_unmute": "Unmute",
        "btn_settings": "Settings",
        "section_important": "Recent Important Messages",
        "btn_listen_summary": "Listen to Summary",
        "col_account": "Account",
        "col_sender": "From",
        "col_subject": "Subject",
        "col_reason": "Why Important?",
        "col_actions": "Action",
        "no_important_emails": "No new important emails. You are all caught up!",
        "backlog_dialog_title": "Older Unread Emails",
        "backlog_dialog_msg": (
            "You have {count} older unread important emails. Would you like to listen to them?"
        ),
        "btn_yes": "Yes, listen",
        "btn_no": "No, skip",
        "tray_tooltip": "MailVoice — Email Assistant",
        "tray_show": "Show Window",
        "tray_exit": "Quit",
        # Settings
        "settings_title": "MailVoice Settings",
        "tab_account": "Email Accounts",
        "accounts_list_title": "Configured accounts:",
        "btn_add_account": "Add account",
        "btn_remove_account": "Remove account",
        "remove_account_title": "Remove account",
        "remove_account_confirm": (
            "Are you sure you want to remove account '{account}'? "
            "This will also remove the stored password."
        ),
        "account_details_title": "Selected account details",
        "acc_status_pwd_saved": "password saved",
        "acc_status_no_pwd": "no password",
        "new_account_label": "New account",
        "account_empty_email_error": "Every account must have an email address specified.",
        "account_invalid_port_error": (
            "Port number for account '{account}' must be between 1 and 65535."
        ),
        "account_ssl_required_error": "Account '{account}' requires secure SSL / TLS connection.",
        "account_duplicate_error": (
            "This account is already on the list: '{account}'. Account addresses must be unique."
        ),
        "account_no_account_selected": "Select an account from the list or click Add account.",
        "step2_multi_hint": ("Tip: You can add additional mailboxes at any time in Settings."),
        "step2_sent_folder": "Sent folder:",
        "tab_analysis": "Evaluation Rules",
        "tab_notifications": "Voice & Notifications",
        "tab_ollama": "AI Model (Ollama)",
        "ollama_detect_btn": "Detect Models",
        "ollama_detecting": "Searching for Ollama server and fetching model list...",
        "ollama_detected_server": "Found server ({source}) — {count} models",
        "ollama_source_local": "this computer",
        "ollama_source_lan": "local network",
        "ollama_not_detected": "No running Ollama server found.",
        "ollama_install_guide": (
            "Install and start Ollama from https://ollama.com. "
            "If needed, specify server URLs in Advanced below."
        ),
        "ollama_general_model_label": "Mail analysis model:",
        "ollama_polish_model_label": "Polish language model:",
        "ollama_same_as_general": "same as general",
        "ollama_recommended_tag": " (recommended)",
        "ollama_recommended_pl_tag": " (recommended for PL)",
        "ollama_show_all_models": "Show all models",
        "ollama_cloud_excluded_hint": (
            "Cloud models (:cloud) are excluded because they send data outside your server."
        ),
        "ollama_model_missing_tag": "not installed",
        "ollama_model_missing_warn": (
            "⚠ Selected model is not installed on the Ollama server. "
            "Mail analysis may fail."
        ),
        "ollama_model_missing_confirm": (
            "Selected model '{model}' is not installed on the Ollama server. "
            "Are you sure you want to save this configuration?"
        ),
        "ollama_check_btn": "Test Model",
        "ollama_checking": "Sending test query to model...",
        "btn_save": "Save Changes",
        "btn_close": "Close",
        "save_success": "Settings saved successfully.",
        # Topic Summary (Digest)
        "tab_messages": "Messages",
        "tab_digest": "Topic Summary",
        "digest_timeframe_label": "Period:",
        "digest_period_week": "Last week (7 days)",
        "digest_period_month": "Last month (30 days)",
        "digest_period_quarter": "Last 3 months (90 days)",
        "btn_refresh_digest": "Refresh summary",
        "digest_group_waiting_me": "Waiting for You",
        "digest_group_waiting_others": "Waiting for Others",
        "digest_group_info": "Information & Closed",
        "digest_empty": "No topics found in the selected period.",
        "digest_no_topics_in_group": "No items in this group.",
        "digest_btn_listen": "Listen",
        "digest_who_to_whom": "Who → To whom",
        "digest_status_loading": "Preparing summary...",
        "settings_digest_days_label": "Default topic summary period (days):",
        "step4_digest_days_label": "Topic summary period (days):",
        # Contact context and AI search
        "context_panel_title": "Sender Context",
        "context_select_mail": "Select a message from the list to view sender context.",
        "context_loading": "Loading context...",
        "context_unknown_sender": ("I do not recognize this sender in your contact history yet."),
        "context_relationship": "Who they are:",
        "context_open_items": "Open matters:",
        "context_last_exchange": "Last exchange:",
        "context_no_open_items": "No open matters.",
        "btn_search_ai": "Search mail (AI)",
        "search_dialog_title": "AI Email Search",
        "search_input_label": "Describe what you are looking for:",
        "search_input_placeholder": "e.g. that email from Kowalski about renovation invoice...",
        "search_period_label": "Search period:",
        "search_period_30": "Last 30 days",
        "search_period_90": "Last 90 days",
        "search_period_365": "Last year (365 days)",
        "btn_run_search": "Search",
        "search_status_searching": "Searching and analyzing emails with AI...",
        "search_no_results": (
            "No matching messages found. Try expanding the timeframe or changing your query."
        ),
        "search_confidence_high": "High confidence",
        "search_confidence_medium": "Medium confidence",
        "search_confidence_low": "Low confidence",
        "search_why_probable": "Why probable:",
        "badge_suspicious": "⚠ Suspicious",
        "suspicious_warning_dialog": (
            "This message has been flagged as potentially dangerous "
            "(phishing / malware). Do not open links or download attachments."
        ),
        "suspicious_reasons_title": "Reasons flagged as suspicious:",
        "error_generic_title": "Something went wrong",
        "error_generic_msg": (
            "Something went wrong. Please try again. If the problem persists, click Details."
        ),
        "btn_details": "Technical details",
        "btn_hide_details": "Hide details",
    },
}

_current_language = "pl"


def set_language(lang: str) -> None:
    """Ustawia bieżący język interfejsu ('pl' lub 'en')."""
    global _current_language
    if lang.lower() in ("pl", "en"):
        _current_language = lang.lower()
    else:
        _current_language = "pl"


def get_language() -> str:
    """Zwraca bieżący język interfejsu."""
    return _current_language


def tr(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Zwraca przetłumaczony ciąg tekstowy dla danego klucza."""
    target_lang = lang.lower() if lang else _current_language
    if target_lang not in _TRANSLATIONS:
        target_lang = "pl"

    table = _TRANSLATIONS[target_lang]
    text = table.get(key)
    if text is None:
        # Fallback do pl lub en lub samego klucza
        text = _TRANSLATIONS["pl"].get(key, key)

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
