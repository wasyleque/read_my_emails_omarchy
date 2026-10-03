"""Stopka „Created by …” i przycisk wsparcia: tylko stałe, zaufane adresy; nic z maili."""

from urllib.parse import urlparse

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mailvoice.ui import about
from mailvoice.ui.i18n import set_language
from mailvoice.ui.main_window import MainWindow
from mailvoice.voice.tts import FakeSpeaker


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_allowlist_has_only_https_github_and_paypal():
    assert about.ALLOWED_URLS == {about.PROJECT_URL, about.DONATE_URL}
    for url in about.ALLOWED_URLS:
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.hostname in {"github.com", "www.paypal.com"}
    assert "wasyleque" in about.PROJECT_URL
    assert "business=wasyl%40o2.pl" in about.DONATE_URL


def test_open_project_link_refuses_anything_not_on_the_allowlist(monkeypatch):
    opened = []
    monkeypatch.setattr(about.QDesktopServices, "openUrl", lambda u: opened.append(u.toString()))
    for evil in (
        "https://evil.example/login",
        "http://github.com/wasyleque/read_my_emails_omarchy",  # inny schemat
        about.PROJECT_URL + "/../x",
        "javascript:alert(1)",
        "",
    ):
        assert about.open_project_link(evil) is False
    assert opened == []
    assert about.open_project_link(about.PROJECT_URL) in (True, None)
    assert opened == [about.PROJECT_URL]


def test_main_window_has_footer_with_author_link_and_donate_button(qapp, monkeypatch):
    set_language("en")
    opened = []
    monkeypatch.setattr(about.QDesktopServices, "openUrl", lambda u: opened.append(u.toString()))
    window = MainWindow(speaker=FakeSpeaker())
    footer = window.findChild(about.QWidget, "footer")
    assert footer is not None
    text = " ".join(lbl.text() for lbl in footer.findChildren(QLabel))
    assert "Created by" in text and "wasyleque" in text and about.PROJECT_URL in text
    buttons = footer.findChildren(QPushButton)
    assert len(buttons) == 1 and "donate" in buttons[0].text().lower()
    label = footer.findChildren(QLabel)[0]
    assert not label.openExternalLinks()  # kliknięcie idzie przez białą listę, nie wprost
    buttons[0].click()
    assert opened == [about.DONATE_URL]
    set_language("pl")


def test_footer_is_translated(qapp):
    set_language("pl")
    footer = about.build_footer()
    widgets = footer.findChildren(QLabel) + footer.findChildren(QPushButton)
    pl_text = " ".join(w.text() for w in widgets)
    assert "GitHubie" in pl_text and "wesprzyj" in pl_text
