"""Stopka okna: autor, link do projektu i przycisk „wesprzyj”.

To JEDYNE miejsce w programie, które otwiera odnośnik w przeglądarce — i tylko jeden z dwóch STAŁYCH
adresów poniżej, po sprawdzeniu białej listy. Żaden adres z maila nie może tu trafić (zasada z
SECURITY.md: nie wchodzimy w odnośniki z poczty). Test statyczny zabrania `openUrl` gdzie indziej.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from mailvoice.ui import theme
from mailvoice.ui.i18n import tr

AUTHOR = "wasyleque"
PROJECT_URL = "https://github.com/wasyleque/read_my_emails_omarchy"
DONATE_URL = (
    "https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=wasyl%40o2.pl"
    "&currency_code=PLN&item_name=MailVoice"
)
ALLOWED_URLS = frozenset({PROJECT_URL, DONATE_URL})


def open_project_link(url: str) -> bool:
    """Otwiera w przeglądarce wyłącznie jeden ze stałych adresów projektu."""
    if url not in ALLOWED_URLS:
        return False
    return QDesktopServices.openUrl(QUrl(url))


def build_footer(parent: QWidget | None = None) -> QWidget:
    """Dyskretna stopka: „Created by wasyleque · Projekt na GitHubie” + przycisk wsparcia."""
    footer = QWidget(parent)
    row = QHBoxLayout(footer)
    row.setContentsMargins(0, 4, 0, 0)

    label = QLabel(
        f"{tr('footer_created_by')} <b>{AUTHOR}</b> · "
        f'<a href="{PROJECT_URL}" style="color:{theme.c("accent")};">{tr("footer_project")}</a>'
    )
    label.setStyleSheet(f"font-size: 11px; color: {theme.c('muted')};")
    label.setTextFormat(Qt.TextFormat.RichText)
    # NIE setOpenExternalLinks: kliknięcie przechodzi przez białą listę w open_project_link().
    label.linkActivated.connect(open_project_link)
    label.setToolTip(PROJECT_URL)
    row.addWidget(label)
    row.addStretch()

    donate = QPushButton(tr("btn_donate"))
    donate.setToolTip(tr("donate_tooltip"))
    donate.setCursor(Qt.CursorShape.PointingHandCursor)
    donate.setStyleSheet(
        f"QPushButton {{ font-size: 11px; padding: 3px 10px; color: {theme.c('accent')}; }}"
    )
    donate.clicked.connect(lambda: open_project_link(DONATE_URL))
    row.addWidget(donate)
    footer.setObjectName("footer")
    return footer
