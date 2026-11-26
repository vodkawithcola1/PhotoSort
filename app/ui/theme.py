"""Motyw jasny/ciemny — tokeny kolorów i arkusz stylów Qt (QSS)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "name": "light",
    "bg": "#F5F5F7",
    "surface": "#FFFFFF",
    "surface2": "#F0F0F3",
    "viewer": "#EBEBEF",
    "text": "#1D1D1F",
    "text2": "#6E6E73",
    "text3": "#A1A1A6",
    "border": "#E2E2E7",
    "hover": "#EAEAEF",
    "pressed": "#DEDEE4",
    "accent": "#0071E3",
    "accent_hover": "#0077ED",
    "accent_soft": "rgba(0,113,227,0.12)",
    "accent_text": "#FFFFFF",
    "danger": "#E5383B",
    "success": "#28A745",
    "shadow": "rgba(0,0,0,0.08)",
    "overlay": "rgba(255,255,255,0.86)",
    "thumb_bg": "#E4E4E9",
}

DARK = {
    "name": "dark",
    "bg": "#1C1C1E",
    "surface": "#242426",
    "surface2": "#2C2C2E",
    "viewer": "#111113",
    "text": "#F5F5F7",
    "text2": "#A1A1A6",
    "text3": "#6E6E73",
    "border": "#363638",
    "hover": "#323235",
    "pressed": "#3A3A3D",
    "accent": "#0A84FF",
    "accent_hover": "#3395FF",
    "accent_soft": "rgba(10,132,255,0.20)",
    "accent_text": "#FFFFFF",
    "danger": "#FF453A",
    "success": "#32D74B",
    "shadow": "rgba(0,0,0,0.4)",
    "overlay": "rgba(36,36,38,0.88)",
    "thumb_bg": "#2C2C2E",
}

_current = dict(LIGHT)


def current() -> dict:
    return _current


def color(key: str) -> QColor:
    v = _current[key]
    if v.startswith("rgba"):
        nums = v[5:-1].split(",")
        c = QColor(int(nums[0]), int(nums[1]), int(nums[2]))
        c.setAlphaF(float(nums[3]))
        return c
    return QColor(v)


def ui_font(size: float = 10.0, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont("Segoe UI Variable Text")
    if not f.exactMatch():
        f = QFont("Segoe UI")
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def apply(app: QApplication, name: str) -> None:
    global _current
    _current = dict(DARK if name == "dark" else LIGHT)
    t = _current
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["surface2"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["text3"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    app.setPalette(pal)
    app.setFont(ui_font(10))
    app.setStyleSheet(stylesheet(t))
    from app.ui import wrap_fix
    wrap_fix.install(app)


def stylesheet(t: dict) -> str:
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {t['text']}; }}
QMainWindow, #Root, #LibraryView, #WelcomeScreen {{ background: {t['bg']}; }}
QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']};
            border-radius: 6px; padding: 5px 8px; }}

/* ---------- panele ---------- */
#Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; }}
#ViewerCard {{ background: {t['viewer']}; border-radius: 14px; }}
#TopBar {{ background: {t['bg']}; }}
#SidePanel {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; }}
#QueuePanel {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; }}
#MetaPanel {{ background: transparent; }}
#Separator {{ background: {t['border']}; max-height: 1px; min-height: 1px; }}

/* ---------- teksty ---------- */
#Title {{ font-size: 15pt; font-weight: 600; }}
#AppName {{ font-size: 12.5pt; font-weight: 700; }}
#H1 {{ font-size: 26pt; font-weight: 700; }}
#H2 {{ font-size: 13pt; font-weight: 600; }}
#SectionTitle {{ font-size: 9pt; font-weight: 600; color: {t['text2']}; letter-spacing: 0.5px; }}
#Muted {{ color: {t['text2']}; }}
#Faint {{ color: {t['text3']}; }}
#Crumb {{ color: {t['text2']}; font-size: 11pt; background: transparent; border: none; padding: 4px 6px; border-radius: 6px; }}
#Crumb:hover {{ background: {t['hover']}; color: {t['text']}; }}
#CrumbCurrent {{ font-size: 11pt; font-weight: 600; padding: 4px 2px; }}
#MetaName {{ font-size: 11pt; font-weight: 600; }}
#MetaValue {{ color: {t['text']}; }}
#MetaKey {{ color: {t['text2']}; }}
#Chip {{ background: {t['surface2']}; border-radius: 9px; color: {t['text2']}; }}
#FilterChip {{ background: {t['accent_soft']}; color: {t['accent']}; border-radius: 11px; padding: 3px 4px 3px 10px; }}
#Toast {{ background: {t['overlay']}; border: 1px solid {t['border']}; border-radius: 12px; }}
#EmptyTitle {{ font-size: 15pt; font-weight: 600; }}
#Error {{ color: {t['danger']}; }}

/* ---------- przyciski ---------- */
QPushButton {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
               padding: 6px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['pressed']}; }}
QPushButton:disabled {{ color: {t['text3']}; }}
QPushButton#Primary {{ background: {t['accent']}; color: {t['accent_text']}; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {t['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {t['pressed']}; color: {t['text3']}; }}
QPushButton#Danger {{ color: {t['danger']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {t['accent']}; padding: 2px 4px; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QPushButton#BigChoice {{ text-align: left; padding: 14px 18px; border-radius: 12px; font-size: 11pt; }}
QPushButton#BigChoice:hover {{ border-color: {t['accent']}; background: {t['surface']}; }}
QFrame#ChoiceCard {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 12px; }}
QFrame#ChoiceCard:hover, QFrame#ChoiceCard:focus {{ border-color: {t['accent']}; }}
QFrame#ChoiceCard QLabel {{ background: transparent; border: none; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: {t['hover']}; }}
QToolButton:pressed {{ background: {t['pressed']}; }}
QToolButton:checked {{ background: {t['accent_soft']}; }}
QToolButton:disabled {{ background: transparent; }}
QToolButton#Pill {{ border: 1px solid {t['border']}; padding: 5px 10px; border-radius: 15px; }}
QToolButton#Pill:checked {{ background: {t['accent_soft']}; color: {t['accent']}; border-color: transparent; }}
QToolButton#OverlayBtn {{ background: {t['overlay']}; border-radius: 18px; padding: 8px; }}
QToolButton#OverlayBtn:hover {{ background: {t['surface']}; }}

/* ---------- pola ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: {t['surface2']}; border: 1px solid transparent; border-radius: 8px;
    padding: 5px 9px; min-height: 20px; selection-background-color: {t['accent']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {t['accent']}; background: {t['surface']}; }}
QLineEdit#Search {{ padding-left: 28px; border-radius: 9px; }}
/* strzałki pól liczbowych: domyślne renderują się źle z arkuszem stylów — liczbę wpisuje się
   z klawiatury lub zmienia kółkiem myszy */
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']};
    border-radius: 8px; padding: 4px; selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}

/* ---------- listy ---------- */
QListView, QListWidget, QTreeWidget {{ background: transparent; border: none; }}
QListWidget#Plain::item {{ padding: 6px 8px; border-radius: 8px; }}
QListWidget#Plain::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
QListWidget#Plain::item:hover {{ background: {t['hover']}; }}

/* ---------- paski ---------- */
QProgressBar {{ background: {t['surface2']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}
QProgressBar#Thin {{ max-height: 5px; min-height: 5px; border-radius: 2px; }}
QProgressBar#Thin::chunk {{ border-radius: 2px; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; border: 1px solid {t['border']}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['text3']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {t['text3']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
QMenu::item:disabled {{ color: {t['text3']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
QDialog {{ background: {t['bg']}; }}
#Popup {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; }}
QTabWidget::pane {{ border: none; }}
QTextEdit, QPlainTextEdit {{ background: {t['surface2']}; border: none; border-radius: 8px; padding: 6px; }}
"""
