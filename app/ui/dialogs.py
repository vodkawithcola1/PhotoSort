"""Proste, czytelne okna dialogowe w stylu aplikacji."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from app.utils.paths import validate_folder_name


class TextPrompt(QDialog):
    def __init__(self, parent: QWidget | None, title: str, label: str, text: str = "",
                 ok_text: str = "Zapisz", validate_name: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.validate_name = validate_name
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("H2")
        lay.addWidget(t)
        l = QLabel(label)
        l.setObjectName("Muted")
        l.setWordWrap(True)
        lay.addWidget(l)
        self.edit = QLineEdit(text)
        self.edit.selectAll()
        self.edit.textChanged.connect(self._check)
        lay.addWidget(self.edit)
        self.err = QLabel("")
        self.err.setObjectName("Error")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Anuluj")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton(ok_text)
        self.ok.setObjectName("Primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self._check()

    def _check(self) -> None:
        msg = validate_folder_name(self.edit.text()) if self.validate_name else None
        if not self.edit.text().strip():
            msg = None
            self.ok.setEnabled(False)
        else:
            self.ok.setEnabled(msg is None)
        self.err.setText(msg or "")

    def value(self) -> str:
        return self.edit.text().strip()

    @staticmethod
    def ask(parent, title: str, label: str, text: str = "", ok_text: str = "Zapisz") -> str | None:
        d = TextPrompt(parent, title, label, text, ok_text)
        if d.exec() == QDialog.DialogCode.Accepted:
            return d.value()
        return None


def info(parent, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(text)
    box.exec()


def warn(parent, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(text)
    box.exec()


def confirm(parent, title: str, text: str, yes: str = "Tak", no: str = "Anuluj") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(text)
    y = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(no, QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is y


def label(text: str, obj: str | None = None, wrap: bool = False, align=None) -> QLabel:
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    l.setWordWrap(wrap)
    if align is not None:
        l.setAlignment(align)
    l.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return l
