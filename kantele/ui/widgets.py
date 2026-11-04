"""Small reusable widgets shared by the per-WM pages."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QVBoxLayout, QWidget,
)


class ColorButton(QPushButton):
    """A button showing a color swatch; clicking opens a color picker."""

    changed = pyqtSignal(str)

    def __init__(self, color: str = "", parent=None):
        super().__init__(parent)
        self.setFixedWidth(110)
        self.clicked.connect(self._pick)
        self.set_color(color)

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        c = QColor(_qt_hex(color)) if color else None
        if c is not None and c.isValid():
            fg = "#000000" if c.lightness() > 128 else "#ffffff"
            self.setStyleSheet(f"background:{c.name()}; color:{fg};")
            self.setText(color)
        else:
            self.setStyleSheet("")
            self.setText(color or "(pick)")

    def _pick(self) -> None:
        start = QColor(_qt_hex(self._color)) if self._color else QColor("#888888")
        c = QColorDialog.getColor(start, self, "Pick a color")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(self._color)


def _qt_hex(color: str) -> str:
    """#RRGGBB[AA] / 0xRRGGBB[AA] -> #RRGGBB for QColor (alpha dropped)."""
    h = color.strip().removeprefix("0x").removeprefix("#")
    return "#" + h[:6]


# Qt key -> X keysym name, for the keys whose Qt text isn't the keysym.
_SPECIAL_KEYS = {
    Qt.Key.Key_Return: "Return", Qt.Key.Key_Enter: "Return",
    Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Backtab: "Tab",
    Qt.Key.Key_Space: "space", Qt.Key.Key_Escape: "Escape",
    Qt.Key.Key_Backspace: "BackSpace", Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "Prior", Qt.Key.Key_PageDown: "Next",
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Print: "Print",
    Qt.Key.Key_Period: "period", Qt.Key.Key_Comma: "comma",
    Qt.Key.Key_Minus: "minus", Qt.Key.Key_Equal: "equal",
    Qt.Key.Key_Plus: "plus", Qt.Key.Key_Slash: "slash",
    Qt.Key.Key_Backslash: "backslash", Qt.Key.Key_Semicolon: "semicolon",
    Qt.Key.Key_Apostrophe: "apostrophe", Qt.Key.Key_QuoteLeft: "grave",
    Qt.Key.Key_BracketLeft: "bracketleft", Qt.Key.Key_BracketRight: "bracketright",
    Qt.Key.Key_VolumeUp: "XF86AudioRaiseVolume",
    Qt.Key.Key_VolumeDown: "XF86AudioLowerVolume",
    Qt.Key.Key_VolumeMute: "XF86AudioMute",
    Qt.Key.Key_MonBrightnessUp: "XF86MonBrightnessUp",
    Qt.Key.Key_MonBrightnessDown: "XF86MonBrightnessDown",
    Qt.Key.Key_MediaPlay: "XF86AudioPlay", Qt.Key.Key_MediaNext: "XF86AudioNext",
    Qt.Key.Key_MediaPrevious: "XF86AudioPrev",
}
_MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_Super_L, Qt.Key.Key_Super_R, Qt.Key.Key_AltGr,
}


def penrose_key(event: QKeyEvent) -> str | None:
    """Converts a key press into penrose's "M-S-x" notation, or None for a
    bare modifier press."""
    key = Qt.Key(event.key())
    if key in _MODIFIER_KEYS:
        return None
    if key in _SPECIAL_KEYS:
        name = _SPECIAL_KEYS[key]
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
        name = f"F{key - Qt.Key.Key_F1 + 1}"
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        name = chr(key).lower()
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(key)
    else:
        return None
    mods = event.modifiers()
    prefix = ""
    for flag, letter in ((Qt.KeyboardModifier.MetaModifier, "M"),
                         (Qt.KeyboardModifier.ControlModifier, "C"),
                         (Qt.KeyboardModifier.AltModifier, "A"),
                         (Qt.KeyboardModifier.ShiftModifier, "S")):
        if mods & flag:
            prefix += letter + "-"
    return prefix + name


class KeyCaptureDialog(QDialog):
    """Press a key combination; returns it in penrose notation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Press a key combination")
        self.result_key: str | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Press the keys now (Super, Ctrl, Alt, Shift + a key).\n"
                             "Note: the window manager may grab some combinations first."))
        self.shown = QLabel("…")
        self.shown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shown.setStyleSheet("font-size: 20pt; padding: 12px;")
        lay.addWidget(self.shown)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        for b in bb.buttons():
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(bb)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        k = penrose_key(event)
        if k:
            self.result_key = k
            self.shown.setText(k)


class EditableTable(QWidget):
    """A table with Add/Remove buttons underneath."""

    def __init__(self, headers: list[str], add_row, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        add = QPushButton("Add")
        rm = QPushButton("Remove")
        add.clicked.connect(lambda: add_row())
        rm.clicked.connect(self._remove)
        btns = QHBoxLayout()
        btns.addWidget(add)
        btns.addWidget(rm)
        btns.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)
        lay.addLayout(btns)

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
