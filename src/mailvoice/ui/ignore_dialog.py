"""Okno „Ignoruj”: wybór, jakie maile zignorować (podobne / od nadawcy / z domeny)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from mailvoice.core.ignore import IGNORE_MODES, rule_for_mail
from mailvoice.ui import theme
from mailvoice.ui.i18n import tr


class IgnoreDialog(QDialog):
    """Pokazuje trzy tryby i podgląd reguły, którą aplikacja zapamięta."""

    def __init__(self, sender: str, subject: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ignore_title"))
        self._sender, self._subject = sender, subject
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("ignore_question")))

        self._group = QButtonGroup(self)
        self._buttons: dict[str, QRadioButton] = {}
        for mode in IGNORE_MODES:
            button = QRadioButton(tr(f"ignore_mode_{mode}"))
            self._group.addButton(button)
            self._buttons[mode] = button
            layout.addWidget(button)
            button.toggled.connect(self._update_preview)
        self._buttons["similar"].setChecked(True)

        self._preview = QLabel("")
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet(f"color: {theme.c('muted')}; font-size: 11px;")
        layout.addWidget(self._preview)
        layout.addWidget(QLabel(tr("ignore_undo_hint")))

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.button(QDialogButtonBox.StandardButton.Ok).setText(tr("ignore_confirm"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self._update_preview()

    def mode(self) -> str:
        for mode, button in self._buttons.items():
            if button.isChecked():
                return mode
        return "similar"

    def _update_preview(self) -> None:
        rule = rule_for_mail(self.mode(), self._sender, self._subject)
        self._preview.setText(f"{tr('ignore_rule_label')} {rule.describe()}")
