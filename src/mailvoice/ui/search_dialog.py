"""Okno dialogowe inteligentnego wyszukiwania wiadomości (AI Email Search)."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.aisearch import SearchHit
from mailvoice.core.friendly_errors import format_friendly_error
from mailvoice.core.service import MailService
from mailvoice.ui import theme
from mailvoice.ui.i18n import get_language, tr
from mailvoice.voice.tts import Speaker, VoiceUnavailable


class SearchWorker(QThread):
    """Wątek roboczy wykonujący wyszukiwanie AI w tle."""

    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(
        self,
        service: MailService,
        query: str,
        days: int | None = None,
        limit: int = 5,
    ) -> None:
        super().__init__()
        self.service = service
        self.query = query
        self.days = days
        self.limit = limit

    def run(self) -> None:
        try:
            hits = self.service.ai_search(
                query=self.query,
                days=self.days,
                limit=self.limit,
            )
            self.results_ready.emit(hits)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class SearchDialog(QDialog):
    """Dialog wyszukiwania maili za pomocą zapytań w języku naturalnym i LLM."""

    def __init__(
        self,
        service: MailService | None = None,
        speaker: Speaker | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.speaker = speaker
        self.worker: SearchWorker | None = None
        self.hits: list[SearchHit] = []

        self.setWindowTitle(tr("search_dialog_title"))
        self.resize(740, 520)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Sekcja wprowadzania zapytania
        lbl_query = QLabel(tr("search_input_label"))
        lbl_query.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(lbl_query)

        query_row = QHBoxLayout()
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText(tr("search_input_placeholder"))
        self.txt_query.returnPressed.connect(self._on_search)
        query_row.addWidget(self.txt_query)

        self.cb_period = QComboBox()
        self.cb_period.addItem(tr("search_period_30"), 30)
        self.cb_period.addItem(tr("search_period_90"), 90)
        self.cb_period.addItem(tr("search_period_365"), 365)
        self.cb_period.setCurrentIndex(0)
        query_row.addWidget(self.cb_period)

        self.btn_search = QPushButton(tr("btn_run_search"))
        self.btn_search.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.btn_search.clicked.connect(self._on_search)
        query_row.addWidget(self.btn_search)
        layout.addLayout(query_row)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px; margin: 4px;")
        layout.addWidget(self.lbl_status)

        # Obszar wyników
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(4, 4, 4, 4)

        self.lbl_empty = QLabel(tr("search_input_placeholder"))
        self.lbl_empty.setStyleSheet(f"color: {theme.c('muted')}; font-size: 12px; margin: 20px;")
        self.results_layout.addWidget(self.lbl_empty)
        self.results_layout.addStretch()

        self.scroll_area.setWidget(self.results_container)
        layout.addWidget(self.scroll_area)

        # Dolny pasek
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton(tr("btn_close"))
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def set_search_query(self, query: str, auto_search: bool = True) -> None:
        """Ustawia tekst zapytania i opcjonalnie uruchamia wyszukiwanie."""
        self.txt_query.setText(query)
        if auto_search and self.service:
            self._on_search()

    def _on_search(self) -> None:
        query = self.txt_query.text().strip()
        if not query or not self.service:
            return
        if self.worker is not None and self.worker.isRunning():
            return

        days = self.cb_period.currentData() or 30
        self.lbl_status.setText(tr("search_status_searching"))
        self.btn_search.setEnabled(False)

        self.worker = SearchWorker(self.service, query=query, days=days)
        self.worker.results_ready.connect(self._on_results_ready)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_results_ready(self, hits: list[SearchHit]) -> None:
        self.btn_search.setEnabled(True)
        self.lbl_status.setText(f"{tr('status_ready')} ({len(hits)} wyników)")
        self.hits = hits
        self._display_hits(hits)

    def _on_error(self, err_msg: str) -> None:
        self.btn_search.setEnabled(True)
        friendly = format_friendly_error(err_msg, lang=get_language())
        self.lbl_status.setText(f"Problem: {friendly}")

    def _display_hits(self, hits: list[SearchHit]) -> None:
        """Renderuje karty znalezionych wiadomości."""
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not hits:
            lbl_none = QLabel(tr("search_no_results"))
            lbl_none.setStyleSheet(f"color: {theme.c('error')}; font-size: 13px; margin: 20px;")
            lbl_none.setWordWrap(True)
            self.results_layout.addWidget(lbl_none)
            self.results_layout.addStretch()
            return

        for hit in hits:
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setObjectName("card")
            card.setStyleSheet(
                f"QFrame#card {{ background-color: {theme.c('card_bg')}; "
                f"border: 1px solid {theme.c('card_border')}; "
                "border-radius: 6px; margin-bottom: 8px; padding: 8px; }"
            )
            card_layout = QVBoxLayout(card)

            # Nagłówek karty z tematem, nadawcą i odznaką pewności
            header_layout = QHBoxLayout()
            title_text = f"<b>{hit.mail_ref.subject}</b>"
            lbl_title = QLabel(title_text)
            lbl_title.setStyleSheet(f"font-size: 13px; color: {theme.c('text')};")
            header_layout.addWidget(lbl_title)
            header_layout.addStretch()

            # Odznaka pewności (badge)
            lbl_badge = QLabel()
            badge_text = {
                "wysoka": tr("search_confidence_high"),
                "średnia": tr("search_confidence_medium"),
            }.get(hit.confidence, tr("search_confidence_low"))
            bg_color, txt_color = theme.badge(hit.confidence)

            lbl_badge.setText(f" {badge_text} ")
            lbl_badge.setStyleSheet(
                f"background-color: {bg_color}; color: {txt_color}; "
                "border-radius: 4px; font-size: 11px; font-weight: bold; padding: 2px 6px;"
            )
            header_layout.addWidget(lbl_badge)

            btn_listen = QPushButton(tr("digest_btn_listen"))
            btn_listen.clicked.connect(lambda _, h=hit: self._listen_to_hit(h))
            header_layout.addWidget(btn_listen)
            card_layout.addLayout(header_layout)

            # Nadawca i data
            dt_str = hit.mail_ref.date[:10] if hit.mail_ref.date else ""
            meta_text = f"Od: {hit.mail_ref.sender} | Data: {dt_str}"
            lbl_meta = QLabel(meta_text)
            lbl_meta.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
            card_layout.addWidget(lbl_meta)

            # Uzasadnienie dopasowania
            if hit.why_probable:
                lbl_why = QLabel(f"<b>{tr('search_why_probable')}</b> {hit.why_probable}")
                lbl_why.setStyleSheet(
                    f"color: {theme.c('link')}; font-size: 12px; margin-top: 4px;"
                )
                lbl_why.setWordWrap(True)
                card_layout.addWidget(lbl_why)

            # Fragment treści / streszczenia
            if hit.snippet:
                lbl_snippet = QLabel(hit.snippet)
                lbl_snippet.setStyleSheet(f"color: {theme.c('text')}; font-size: 12px;")
                lbl_snippet.setWordWrap(True)
                card_layout.addWidget(lbl_snippet)

            self.results_layout.addWidget(card)

        self.results_layout.addStretch()

    def _listen_to_hit(self, hit: SearchHit) -> None:
        """Odtwarza na głos podsumowanie i uzasadnienie trafienia."""
        if not self.speaker:
            return
        lang = get_language()
        if lang == "pl":
            text = (
                f"Wiadomość od {hit.mail_ref.sender}. Temat: {hit.mail_ref.subject}. "
                f"Dlaczego pasuje: {hit.why_probable}. Treść: {hit.snippet}"
            )
        else:
            text = (
                f"Message from {hit.mail_ref.sender}. Subject: {hit.mail_ref.subject}. "
                f"Why relevant: {hit.why_probable}. Content: {hit.snippet}"
            )
        try:
            self.speaker.speak(" ".join(text.split()), lang=lang)
        except VoiceUnavailable as exc:
            QMessageBox.warning(self, "MailVoice", str(exc))
