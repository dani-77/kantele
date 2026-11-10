"""Settings pages for pwm and wmd77 (same config.toml format)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFontComboBox, QSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QFont

from ..backends import pwm
from .widgets import ColorButton, EditableTable, KeyCaptureDialog


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: palette(placeholder-text);")
    return lbl


class ThemeTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        top = QFormLayout()
        self.active = QComboBox()
        self.active.currentTextChanged.connect(self._preview)
        top.addRow("Active theme:", self.active)
        lay.addLayout(top)

        self.preview = QLabel()
        self.preview.setMinimumHeight(34)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.preview)

        box = QGroupBox("Your own themes")
        bl = QHBoxLayout(box)
        self.names = QListWidget()
        self.names.setMaximumWidth(180)
        self.names.currentTextChanged.connect(self._show_palette)
        side = QVBoxLayout()
        side.addWidget(self.names)
        b_add, b_rm = QPushButton("New…"), QPushButton("Delete")
        b_add.clicked.connect(self._new)
        b_rm.clicked.connect(self._delete)
        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_rm)
        side.addLayout(row)
        bl.addLayout(side)

        form = QFormLayout()
        self.color_btns: dict[str, ColorButton] = {}
        labels = {"black": "Background", "white": "Text", "grey": "Inactive",
                  "accent": "Accent"}
        for f in pwm.THEME_FIELDS:
            b = ColorButton()
            b.changed.connect(lambda v, f=f: self._edit(f, v))
            self.color_btns[f] = b
            form.addRow(f"{labels[f]} ({f}):", b)
        self.font = QFontComboBox()
        self.font.currentFontChanged.connect(lambda fnt: self._edit("font", fnt.family()))
        form.addRow("Font:", self.font)
        self.editor = QWidget()
        self.editor.setLayout(form)
        bl.addWidget(self.editor)
        lay.addWidget(box)
        lay.addWidget(_note(
            "Reusing a built-in name (e.g. dracula) overrides that theme. "
            "Built-in themes: " + ", ".join(pwm.BUILTIN_THEMES) + "."))
        lay.addStretch()
        self.palettes: dict[str, dict[str, str]] = {}
        self._loading = False

    def load(self, s: pwm.Settings) -> None:
        self._loading = True
        self.palettes = {k: dict(v) for k, v in s.palettes.items()}
        self.names.clear()
        self.names.addItems(self.palettes)
        self._refresh_active(s.theme or pwm.DEFAULT_THEME)
        self.editor.setEnabled(bool(self.palettes))
        if self.palettes:
            self.names.setCurrentRow(0)
        self._loading = False
        self._preview()

    def store(self, s: pwm.Settings) -> None:
        a = self.active.currentText()
        s.theme = None if a == pwm.DEFAULT_THEME and a not in self.palettes else a
        s.palettes = {k: dict(v) for k, v in self.palettes.items()}

    def _refresh_active(self, want: str) -> None:
        self.active.blockSignals(True)
        self.active.clear()
        names = list(pwm.BUILTIN_THEMES) + [n for n in self.palettes
                                             if n not in pwm.BUILTIN_THEMES]
        self.active.addItems(names)
        if want not in names:
            self.active.addItem(want)
        self.active.setCurrentText(want)
        self.active.blockSignals(False)

    def _colors(self, name: str) -> dict[str, str]:
        if name in self.palettes:
            return self.palettes[name]
        b = pwm.BUILTIN_THEMES.get(name, pwm.BUILTIN_THEMES[pwm.DEFAULT_THEME])
        return dict(zip(pwm.THEME_FIELDS, b))

    def _preview(self, *_):
        c = self._colors(self.active.currentText())
        hx = {k: "#" + v.removeprefix("0x").removeprefix("#")[:6] for k, v in c.items()
              if k in pwm.THEME_FIELDS and v}
        if len(hx) < 4:
            self.preview.setText("")
            return
        self.preview.setText(
            f"<span style='background:{hx['accent']};color:{hx['black']}'>&nbsp;1&nbsp;</span>"
            f"<span style='color:{hx['grey']}'>&nbsp;2&nbsp;3&nbsp;4&nbsp;</span>"
            f"<span style='color:{hx['white']}'>&nbsp;[Side]&nbsp;&nbsp;bar preview</span>")
        self.preview.setStyleSheet(f"background:{hx['black']}; padding:6px;"
                                   f"border-bottom: 3px solid {hx['accent']};")

    def _show_palette(self, name: str) -> None:
        if not name:
            return
        self._loading = True
        p = self.palettes[name]
        for f, b in self.color_btns.items():
            b.set_color(p.get(f, ""))
        self.font.setCurrentFont(QFont(p.get("font") or pwm.DEFAULT_FONT))
        self._loading = False

    def _edit(self, f: str, v: str) -> None:
        name = self.names.currentItem().text() if self.names.currentItem() else None
        if self._loading or not name:
            return
        self.palettes[name][f] = v
        self._preview()

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "New theme", "Theme name:")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.palettes:
            return
        base = self._colors(self.active.currentText())
        self.palettes[name] = {k: base[k] for k in pwm.THEME_FIELDS}
        self.palettes[name]["font"] = pwm.DEFAULT_FONT
        self.names.addItem(name)
        self.names.setCurrentRow(self.names.count() - 1)
        self.editor.setEnabled(True)
        self._refresh_active(self.active.currentText())

    def _delete(self) -> None:
        it = self.names.currentItem()
        if not it:
            return
        name = it.text()
        del self.palettes[name]
        self.names.takeItem(self.names.row(it))
        cur = self.active.currentText()
        self._refresh_active(pwm.DEFAULT_THEME if cur == name else cur)
        self.editor.setEnabled(bool(self.palettes))
        self._preview()


class AppsTab(QWidget):
    LABELS = {"terminal": "Terminal", "launcher": "Launcher",
              "locker": "Screen locker", "startup_script": "Startup script"}

    def __init__(self, flavor: pwm.Flavor):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for k, default in flavor.apps.items():
            e = QLineEdit()
            e.setPlaceholderText(f"default: {default}")
            self.edits[k] = e
            form.addRow(self.LABELS[k] + ":", e)
        lay.addLayout(form)
        lay.addWidget(_note(
            f"Leave a field empty to use {flavor.name}'s default."
            + (" The startup script receives the active theme name as its first argument."
               if flavor.bar == "widgets" else "")))
        lay.addStretch()

    def load(self, s: pwm.Settings) -> None:
        for k, e in self.edits.items():
            e.setText(s.apps.get(k, ""))

    def store(self, s: pwm.Settings) -> None:
        s.apps = {k: e.text().strip() for k, e in self.edits.items() if e.text().strip()}


class WindowRulesTab(QWidget):
    def __init__(self, flavor: pwm.Flavor):
        super().__init__()
        lay = QVBoxLayout(self)
        if flavor.window_rules:
            note = ("Which window class opens on which workspace. Your rules are laid over "
                    f"{flavor.name}'s built-in ones by class: " + ", ".join(
                        f"{c}→{w}" for c, w in flavor.window_rules) + ".")
        else:
            note = (f"Which window class opens on which workspace. {flavor.name} has no "
                    "built-in rules.")
        lay.addWidget(_note(note))
        self.et = EditableTable(["Window class", "Workspace"], self._add)
        lay.addWidget(self.et)

    def _add(self, cls: str = "", ws: str = "1") -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(cls))
        cb = QComboBox()
        cb.addItems(pwm.WORKSPACES)
        if ws not in pwm.WORKSPACES:
            cb.addItem(ws)
        cb.setCurrentText(ws)
        t.setCellWidget(r, 1, cb)

    def load(self, s: pwm.Settings) -> None:
        self.et.table.setRowCount(0)
        for c, w in s.window_rules:
            self._add(c, w)

    def store(self, s: pwm.Settings) -> None:
        t = self.et.table
        s.window_rules = [((t.item(r, 0).text() if t.item(r, 0) else "").strip(),
                           t.cellWidget(r, 1).currentText()) for r in range(t.rowCount())]


class FloatRulesTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Windows of these classes float centered instead of tiling. Size is a "
            "fraction of the screen (0 = pwm default, 0.6)."))
        self.et = EditableTable(["Window class", "Width", "Height"], self._add)
        lay.addWidget(self.et)

    def _spin(self, v: float | None) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 1.0)
        sp.setSingleStep(0.05)
        sp.setDecimals(2)
        sp.setSpecialValueText("default")
        sp.setValue(v or 0.0)
        return sp

    def _add(self, cls: str = "", w: float | None = None, h: float | None = None) -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(cls))
        t.setCellWidget(r, 1, self._spin(w))
        t.setCellWidget(r, 2, self._spin(h))

    def load(self, s: pwm.Settings) -> None:
        self.et.table.setRowCount(0)
        for fr in s.float_rules:
            self._add(fr.cls, fr.width, fr.height)

    def store(self, s: pwm.Settings) -> None:
        t = self.et.table

        def val(r, c):
            v = round(t.cellWidget(r, c).value(), 2)
            return v or None

        s.float_rules = [pwm.FloatRule((t.item(r, 0).text() if t.item(r, 0) else "").strip(),
                                       val(r, 1), val(r, 2)) for r in range(t.rowCount())]


class BarTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note("Tick the widgets to show and drag them into order."))
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        lay.addWidget(self.list)
        reset = QPushButton("Reset to pwm's default")
        reset.clicked.connect(lambda: self._fill(None))
        row = QHBoxLayout()
        row.addWidget(reset)
        row.addStretch()
        lay.addLayout(row)

    def _fill(self, widgets: list[str] | None) -> None:
        on = widgets if widgets is not None else pwm.BAR_WIDGETS
        order = on + [w for w in pwm.BAR_WIDGETS if w not in on]
        self.list.clear()
        for w in order:
            it = QListWidgetItem(w)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Checked if w in on else Qt.CheckState.Unchecked)
            self.list.addItem(it)

    def load(self, s: pwm.Settings) -> None:
        self._explicit = s.bar_widgets is not None
        self._fill(s.bar_widgets)

    def store(self, s: pwm.Settings) -> None:
        on = [self.list.item(i).text() for i in range(self.list.count())
              if self.list.item(i).checkState() == Qt.CheckState.Checked]
        # keep an explicit list the file already had, even if it matches the
        # default; only leave the key out when it wasn't there to begin with
        s.bar_widgets = None if on == pwm.BAR_WIDGETS and not self._explicit else on


class Wmd77BarTab(QWidget):
    """wmd77's own [bar]: on/off, size, position, and room for an external bar."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.enable = QComboBox()
        self.enable.addItems(["default (on)", "on", "off"])
        form.addRow("Built-in bar:", self.enable)
        self.position = QComboBox()
        self.position.addItems(["default (top)", "top", "bottom"])
        form.addRow("Position:", self.position)
        self.spins: dict[str, QSpinBox] = {}
        labels = {"height": "Height (px)", "font_size": "Font size",
                  "reserve_top": "Room kept free at the top (px)"}
        for k, (lo, hi) in pwm.WMD77_BAR_LIMITS.items():
            sp = QSpinBox()
            sp.setRange(lo - 1, hi)       # lo - 1 = "default", i.e. leave the key out
            sp.setSpecialValueText("default")
            self.spins[k] = sp
            form.addRow(labels[k] + ":", sp)
        lay.addLayout(form)
        lay.addWidget(_note(
            "Turn the built-in bar off to run an external one (polybar, lemonbar, ...) "
            "from your startup script, and keep room for it at the top. The room "
            "defaults to 18 px with the built-in bar at the top, 0 otherwise. The bar "
            "text comes from /etc/xdg/wmd77/bar.sh."))
        lay.addStretch()

    def load(self, s: pwm.Settings) -> None:
        b = s.bar
        self.enable.setCurrentIndex(0 if "enable" not in b else (1 if b["enable"] else 2))
        self.position.setCurrentIndex({"top": 1, "bottom": 2}.get(b.get("position"), 0))
        for k, sp in self.spins.items():
            v = b.get(k)
            sp.setValue(v if isinstance(v, int) else sp.minimum())

    def store(self, s: pwm.Settings) -> None:
        b: dict[str, object] = {}
        if self.enable.currentIndex():
            b["enable"] = self.enable.currentIndex() == 1
        if self.position.currentIndex():
            b["position"] = self.position.currentText()
        for k, sp in self.spins.items():
            if sp.value() != sp.minimum():
                b[k] = sp.value()
        s.bar = b


class KeyboardTab(QWidget):
    """[keyboard]: XKB layout/variant/model/options and key repeat, the same
    settings wasp and spitfire have."""

    LABELS = {"layout": "Layout (e.g. us, pt)", "variant": "Variant",
              "model": "Model (e.g. pc105)", "options": "Options (e.g. caps:escape)",
              "repeat_delay": "Repeat delay (ms)", "repeat_rate": "Repeat rate (per second)"}

    def __init__(self, flavor: pwm.Flavor):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for k in pwm.KEYBOARD_STR:
            e = QLineEdit()
            e.setPlaceholderText("unchanged")
            self.edits[k] = e
            form.addRow(self.LABELS[k] + ":", e)
        self.spins: dict[str, QSpinBox] = {}
        for k, (lo, hi) in pwm.KEYBOARD_LIMITS.items():
            sp = QSpinBox()
            sp.setRange(lo - 1, hi)       # lo - 1 = "unchanged", i.e. leave the key out
            sp.setSpecialValueText("unchanged")
            self.spins[k] = sp
            form.addRow(self.LABELS[k] + ":", sp)
        lay.addLayout(form)
        lay.addWidget(_note(
            f"Empty fields leave the keyboard as the X server set it up; {flavor.name} only "
            "runs setxkbmap / xset r rate for what you fill in. Several layouts (with one "
            "variant each) and several options are separated by commas, e.g. pt,us and "
            "grp:alt_shift_toggle,caps:escape. Setting only one of the repeat values uses "
            "the X default for the other (660 ms, 25 per second)."))
        lay.addStretch()

    def load(self, s: pwm.Settings) -> None:
        kb = s.keyboard
        for k, e in self.edits.items():
            e.setText(str(kb.get(k, "")))
        for k, sp in self.spins.items():
            v = kb.get(k)
            sp.setValue(v if isinstance(v, int) else sp.minimum())

    def store(self, s: pwm.Settings) -> None:
        kb: dict[str, object] = {}
        for k, e in self.edits.items():
            # "pt, us" -> "pt,us": what setxkbmap expects. Empty items stay
            # (",nodeadkeys" is the second layout's variant).
            v = ",".join(p.strip() for p in e.text().split(","))
            if v.strip(","):
                kb[k] = v
        for k, sp in self.spins.items():
            if sp.value() != sp.minimum():
                kb[k] = sp.value()
        s.keyboard = kb


class KeysTab(QWidget):
    def __init__(self, flavor: pwm.Flavor):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            f"Your keybindings. Each one replaces {flavor.name}'s default for the same key; "
            "every other default stays. Keys use penrose notation: M = Super, "
            "S = Shift, C = Ctrl, A = Alt (e.g. M-S-Return)."))
        self.et = EditableTable(["Key", "Action", "Argument"], self._add)
        hh = self.et.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.et.table.setColumnWidth(0, 210)
        lay.addWidget(self.et, 1)

        box = QGroupBox(f"{flavor.name}'s built-in keys")
        bl = QVBoxLayout(box)
        self.defaults = QTableWidget(len(pwm.DEFAULT_BINDS), 3)
        self.defaults.setHorizontalHeaderLabels(["Key", "Action", "Argument"])
        self.defaults.horizontalHeader().setStretchLastSection(True)
        self.defaults.verticalHeader().setVisible(False)
        self.defaults.setMinimumHeight(170)
        self.defaults.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.defaults.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for r, (k, a, arg) in enumerate(pwm.DEFAULT_BINDS):
            for c, v in enumerate((k, f"{a} — {pwm.ACTIONS[a][0]}", arg or "")):
                self.defaults.setItem(r, c, QTableWidgetItem(v))
        self.defaults.resizeColumnsToContents()
        bl.addWidget(self.defaults)
        override = QPushButton("Override selected")
        override.clicked.connect(self._override)
        row = QHBoxLayout()
        row.addWidget(override)
        row.addStretch()
        bl.addLayout(row)
        lay.addWidget(box, 1)

    def _add(self, key: str = "", action: str = "spawn", arg: str | None = None) -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        cell = QWidget()
        h = QHBoxLayout(cell)
        h.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(key)
        cap = QToolButton()
        cap.setText("⌨")
        cap.setToolTip("Record a key combination")
        cap.clicked.connect(lambda: self._capture(edit))
        h.addWidget(edit)
        h.addWidget(cap)
        t.setCellWidget(r, 0, cell)
        cb = QComboBox()
        for a, (desc, _) in pwm.ACTIONS.items():
            cb.addItem(f"{a} — {desc}", a)
        idx = cb.findData(action)
        if idx < 0:
            cb.addItem(action, action)
            idx = cb.count() - 1
        cb.setCurrentIndex(idx)
        t.setCellWidget(r, 1, cb)
        argedit = QLineEdit(arg or "")
        t.setCellWidget(r, 2, argedit)

        def sync(_=None):
            kind = pwm.ACTIONS.get(cb.currentData(), ("", None))[1]
            argedit.setEnabled(kind is not None)
            argedit.setPlaceholderText({"int": "number, e.g. 1 or -1",
                                        "command": "command to run"}.get(kind, ""))
        cb.currentIndexChanged.connect(sync)
        sync()
        t.resizeRowsToContents()

    def _capture(self, edit: QLineEdit) -> None:
        d = KeyCaptureDialog(self)
        if d.exec() and d.result_key:
            edit.setText(d.result_key)

    def _override(self) -> None:
        rows = sorted({i.row() for i in self.defaults.selectedIndexes()})
        for r in rows:
            k, a, arg = pwm.DEFAULT_BINDS[r]
            self._add(k, a, arg)

    def load(self, s: pwm.Settings) -> None:
        self.et.table.setRowCount(0)
        for b in s.binds:
            self._add(b.key, b.action, b.arg)

    def store(self, s: pwm.Settings) -> None:
        t = self.et.table
        out = []
        for r in range(t.rowCount()):
            key = t.cellWidget(r, 0).findChild(QLineEdit).text().strip()
            action = t.cellWidget(r, 1).currentData()
            argw = t.cellWidget(r, 2)
            arg = argw.text().strip() if argw.isEnabled() and argw.text().strip() else None
            out.append(pwm.Bind(key, action, arg))
        s.binds = out


class PwmPage(QWidget):
    flavor = pwm.PWM

    def __init__(self, path=None):
        super().__init__()
        fl = self.flavor
        self.title = fl.name
        self.cfg = pwm.Config(path, fl)
        lay = QVBoxLayout(self)
        head = QLabel(f"<b>{fl.name}</b> — {self.cfg.path}"
                      + ("" if self.cfg.existed else " <i>(will be created)</i>"))
        lay.addWidget(head)
        self.tabs = QTabWidget()
        self.parts = [
            ("Theme", ThemeTab()), ("Applications", AppsTab(fl)),
            ("Workspaces", WindowRulesTab(fl)), ("Floating", FloatRulesTab()),
            ("Bar", BarTab() if fl.bar == "widgets" else Wmd77BarTab()),
            ("Keyboard", KeyboardTab(fl)), ("Keybindings", KeysTab(fl)),
        ]
        for name, w in self.parts:
            self.tabs.addTab(w, name)
        lay.addWidget(self.tabs)
        self.reload()

    def reload(self) -> None:
        self.cfg = pwm.Config(self.cfg.path, self.flavor)
        s = self.cfg.read()
        for _, w in self.parts:
            w.load(s)

    def collect(self) -> pwm.Settings:
        s = self.cfg.read()
        for _, w in self.parts:
            w.store(s)
        return s

    def save(self, apply: bool) -> str | None:
        """Validates and writes. Returns a status message, or None if the
        user has to fix something first."""
        s = self.collect()
        errs = pwm.validate(s, self.flavor)
        if errs:
            QMessageBox.warning(self, "Please fix these first",
                                "\n".join(f"• {e}" for e in errs))
            return None
        self.cfg.apply(s)
        backup = self.cfg.save()
        msg = pwm.reload_running(self.flavor) if apply else "Saved."
        if backup:
            msg += f" (Your original file was kept as {backup.name}.)"
        return msg


class Wmd77Page(PwmPage):
    flavor = pwm.WMD77
