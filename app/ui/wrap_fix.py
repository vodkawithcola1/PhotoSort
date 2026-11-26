"""Poprawka dla zawijanych napisów Qt (QLabel z wordWrap).

Qt nie zawsze rezerwuje dla zawijanego napisu wysokość potrzebną na wszystkie
linie (szczególnie gdy napis jest wyśrodkowany lub przy skalowaniu ekranu
125%/150%) — tekst bywa wtedy ucinany od góry i od dołu. Ten filtr zdarzeń
po każdej zmianie rozmiaru ustawia minimalną wysokość napisu na wartość
wyliczoną dla jego rzeczywistej szerokości.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QLabel


class _WrapFix(QObject):
    def eventFilter(self, obj, e) -> bool:
        if e.type() in (QEvent.Type.Resize, QEvent.Type.Show) and isinstance(obj, QLabel) and obj.wordWrap():
            _fit(obj)
        return False


def _fit(label: QLabel) -> None:
    w = label.width()
    if w <= 0:
        return
    h = label.heightForWidth(w)
    if h <= 0:
        return
    if label.minimumHeight() != h:
        label.setMinimumHeight(h)
        if label.parentWidget() and label.parentWidget().layout():
            label.parentWidget().layout().invalidate()


def refit(label: QLabel) -> None:
    """Wywołaj po zmianie tekstu napisu, który nie zmienia rozmiaru (np. pusty stan)."""
    label.setMinimumHeight(0)
    QTimer.singleShot(0, lambda: _fit(label) if label is not None else None)


_installed: _WrapFix | None = None


def install(app: QApplication) -> None:
    global _installed
    if _installed is None:
        _installed = _WrapFix(app)
        app.installEventFilter(_installed)
