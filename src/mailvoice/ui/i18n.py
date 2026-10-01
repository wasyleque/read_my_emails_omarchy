"""Prosty moduł internacjonalizacji (i18n) bez zależności od Qt Linguist."""

from typing import Any

# Słownik tłumaczeń dla języków polskiego (pl) i angielskiego (en)
_TRANSLATIONS: dict[str, dict[str, str]] = {
    "pl": {
        # Kreator
        "wizard_title": "Kreator konfiguracji MailVoice",
        "step1_title": "Witaj w MailVoice",
        "step1_intro": (
            "Twój inteligentny asystent poczty, "
            "który przeczyta najważniejsze wiadomości na głos."
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
            "Aplikacja została skonfigurowana. "
            "Kliknij „Zakończ”, aby rozpocząć pracę asystenta."
        ),
        "btn_next": "Dalej >",
        "btn_back": "< Wstecz",
        "btn_finish": "Zakończ",
        "btn_cancel": "Anuluj",
        # Okno główne
        "app_title": "MailVoice",
        "status_ready": "Wszystko działa poprawnie",
        "status_checking": "Sprawdzam nową pocztę...",
        "status_last_check": "Ostatnie sprawdzenie:",
        "status_never": "brak danych",
        "btn_check_now": "Sprawdź teraz",
        "btn_mute": "Wycisz przypomnienia",
        "btn_unmute": "Wyłącz wyciszenie",
        "btn_settings": "Ustawienia",
        "section_important": "Ostatnie ważne wiadomości",
        "btn_listen_summary": "Posłuchaj streszczenia",
        "col_sender": "Od",
        "col_subject": "Temat",
        "col_reason": "Dlaczego ważny?",
        "col_actions": "Akcja",
        "no_important_emails": "Brak nowych ważnych maili. Wszystko pod kontrolą!",
        "backlog_dialog_title": "Zaległe nieprzeczytane wiadomości",
        "backlog_dialog_msg": (
            "Masz {count} starszych nieprzeczytanych ważnych wiadomości. "
            "Czy chcesz ich wysłuchać?"
        ),
        "btn_yes": "Tak, posłuchaj",
        "btn_no": "Nie, pomiń",
        "tray_tooltip": "MailVoice — Asystent pocztowy",
        "tray_show": "Pokaż okno",
        "tray_exit": "Zakończ program",
        # Ustawienia
        "settings_title": "Ustawienia MailVoice",
        "tab_account": "Konto pocztowe",
        "tab_analysis": "Ocenianie ważności",
        "tab_notifications": "Głos i powiadomienia",
        "tab_ollama": "Model AI (Ollama)",
        "btn_save": "Zapisz zmiany",
        "btn_close": "Zamknij",
        "save_success": "Ustawienia zostały pomyślnie zapisane.",
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
        "status_last_check": "Last check:",
        "status_never": "none",
        "btn_check_now": "Check Now",
        "btn_mute": "Mute Reminders",
        "btn_unmute": "Unmute",
        "btn_settings": "Settings",
        "section_important": "Recent Important Messages",
        "btn_listen_summary": "Listen to Summary",
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
        "tab_account": "Email Account",
        "tab_analysis": "Evaluation Rules",
        "tab_notifications": "Voice & Notifications",
        "tab_ollama": "AI Model (Ollama)",
        "btn_save": "Save Changes",
        "btn_close": "Close",
        "save_success": "Settings saved successfully.",
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
