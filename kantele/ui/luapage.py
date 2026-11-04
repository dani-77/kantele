"""Settings pages for the Lua-configured WMs (wasp, spitfire)."""

from __future__ import annotations

import shlex

from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from ..backends import spitfire, wasp
from ..backends.luautil import LuaError, Spec
from .widgets import ColorButton, EditableTable, KeyCaptureDialog


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: palette(placeholder-text);")
    return lbl


def _show(spec: Spec, v) -> str:
    if spec.kind == "argv":
        return shlex.join(v)
    if spec.kind == "bool":
        return "on" if v else "off"
    return str(v)


class Field:
    """One editable setting plus a reset button that brings back config.lua's
    value (which drops the setting from kantele.lua)."""

    def __init__(self, spec: Spec):
        self.spec = spec
        self.base = spec.default
        k = spec.kind
        if k == "int":
            w = QSpinBox()
            w.setRange(int(spec.lo), int(spec.hi))
            w.valueChanged.connect(self._changed)
        elif k == "float":
            w = QDoubleSpinBox()
            w.setRange(spec.lo, spec.hi)
            w.setDecimals(2)
            w.setSingleStep(0.05)
            w.valueChanged.connect(self._changed)
        elif k == "bool":
            w = QCheckBox()
            w.toggled.connect(self._changed)
        elif k == "color":
            w = ColorButton()
            w.changed.connect(self._changed)
        elif k == "choice":
            w = QComboBox()
            w.addItems(spec.choices)
            w.currentTextChanged.connect(self._changed)
        else:
            w = QLineEdit()
            w.textChanged.connect(self._changed)
        self.widget = w
        self.reset = QToolButton()
        self.reset.setText("↺")
        self.reset.clicked.connect(lambda: self.set(self.base))
        self.label = QLabel(spec.label + ":")
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w)
        h.addWidget(self.reset)
        h.addStretch()
        self.row = row

    def set(self, v) -> None:
        w, k = self.widget, self.spec.kind
        if k == "int":
            w.setValue(int(v))
        elif k == "float":
            w.setValue(float(v))
        elif k == "bool":
            w.setChecked(bool(v))
        elif k == "color":
            w.set_color(str(v))
        elif k == "choice":
            if w.findText(str(v)) < 0:
                w.addItem(str(v))
            w.setCurrentText(str(v))
        elif k == "argv":
            w.setText(shlex.join(v))
        else:
            w.setText(str(v))
        self._changed()

    def get(self):
        w, k = self.widget, self.spec.kind
        if k in ("int", "float"):
            return w.value()
        if k == "bool":
            return w.isChecked()
        if k == "color":
            return w.color()
        if k == "choice":
            return w.currentText()
        if k == "argv":
            try:
                return shlex.split(w.text())
            except ValueError:
                return [w.text()]
        return w.text()

    def _changed(self, *_):
        mine = self.get() != self.base
        text = self.spec.label + ":"
        self.label.setText(f"<b>{text}</b>" if mine else text)
        self.reset.setEnabled(mine)
        self.reset.setToolTip(f"Back to config.lua's value: {_show(self.spec, self.base)}")


class SpecTab(QWidget):
    def __init__(self, specs: list[Spec], note: str = ""):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = [Field(s) for s in specs]
        for f in self.fields:
            form.addRow(f.label, f.row)
        lay.addLayout(form)
        if note:
            lay.addWidget(_note(note))
        lay.addStretch()

    def load(self, s) -> None:
        for f in self.fields:
            f.base = s.base[f.spec.path]
            f.set(s.values[f.spec.path])

    def store(self, s) -> None:
        for f in self.fields:
            s.values[f.spec.path] = f.get()


WASP_NOTES = {
    "Windows": "Border width and corner radius reach already open windows the next time "
               "they move or resize.",
    "Effects": "Turning blur on or off only affects windows opened afterwards.",
    "Applications": "Commands are split like a shell would, e.g.  foot -e fish.",
}


class KeysTab(QWidget):
    def __init__(self, page: "LuaPage"):
        super().__init__()
        self.page = page
        self.be = page.backend
        lay = QVBoxLayout(self)
        lay.addWidget(_note(page.keys_note))
        self.et = EditableTable(["Key", "Action", "Argument"], self._add)
        hh = self.et.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.et.table.setColumnWidth(0, 230)
        lay.addWidget(self.et, 1)

        box = QGroupBox("config.lua's keys")
        bl = QVBoxLayout(box)
        self.base = QTableWidget(0, 3)
        self.base.setHorizontalHeaderLabels(["Key", "Action", "Argument"])
        self.base.horizontalHeader().setStretchLastSection(True)
        self.base.verticalHeader().setVisible(False)
        self.base.setMinimumHeight(170)
        self.base.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.base.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        bl.addWidget(self.base)
        row = QHBoxLayout()
        override = QPushButton("Override selected")
        override.clicked.connect(lambda: self._from_base(disable=False))
        disable = QPushButton("Disable selected")
        disable.clicked.connect(lambda: self._from_base(disable=True))
        row.addWidget(override)
        row.addWidget(disable)
        row.addStretch()
        bl.addLayout(row)
        lay.addWidget(box, 1)
        self.base_binds: list = []

    def _add(self, combo: str = "", action: str = "spawn", arg: str = "") -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        cell = QWidget()
        h = QHBoxLayout(cell)
        h.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(combo)
        cap = QToolButton()
        cap.setText("⌨")
        cap.setToolTip("Record a key combination")
        cap.clicked.connect(lambda: self._capture(edit))
        h.addWidget(edit)
        h.addWidget(cap)
        t.setCellWidget(r, 0, cell)
        cb = QComboBox()
        for a, (desc, _) in self.be.ACTIONS.items():
            cb.addItem(f"{a} — {desc}", a)
        idx = cb.findData(action)
        if idx < 0:
            cb.addItem(action, action)
            idx = cb.count() - 1
        cb.setCurrentIndex(idx)
        t.setCellWidget(r, 1, cb)
        argedit = QLineEdit(arg)
        t.setCellWidget(r, 2, argedit)

        hints = self.be.HINTS

        def sync(_=None):
            kind = self.be.ACTIONS.get(cb.currentData(), ("", None))[1]
            argedit.setEnabled(kind is not None)
            argedit.setPlaceholderText(hints.get(kind, ""))
        cb.currentIndexChanged.connect(sync)
        sync()
        t.resizeRowsToContents()

    def _capture(self, edit: QLineEdit) -> None:
        d = KeyCaptureDialog(self)
        if d.exec() and d.result_key:
            edit.setText(self.be.combo_from_penrose(d.result_key, self.page.modkey()))

    def _from_base(self, disable: bool) -> None:
        for r in sorted({i.row() for i in self.base.selectedIndexes()}):
            b = self.base_binds[r]
            if disable:
                self._add(b.combo, "none", "")
            elif b.action in self.be.ACTIONS:
                self._add(b.combo, b.action, b.arg)
            else:  # a Lua function: keep the key, pick a new action
                self._add(b.combo, "spawn", "")

    def load(self, s) -> None:
        self.base_binds = s.base_binds
        self.base.setRowCount(len(s.base_binds))
        for r, b in enumerate(s.base_binds):
            if b.action in self.be.ACTIONS:
                action = f"{b.action} — {self.be.ACTIONS[b.action][0]}"
            else:
                action = "Lua function"
            for c, v in enumerate((b.combo, action, b.arg)):
                self.base.setItem(r, c, QTableWidgetItem(v))
        self.base.resizeColumnsToContents()
        self.et.table.setRowCount(0)
        for b in s.binds:
            self._add(b.combo, b.action, b.arg)

    def store(self, s) -> None:
        t = self.et.table
        out = []
        for r in range(t.rowCount()):
            combo = t.cellWidget(r, 0).findChild(QLineEdit).text().strip()
            action = t.cellWidget(r, 1).currentData()
            argw = t.cellWidget(r, 2)
            arg = argw.text().strip() if argw.isEnabled() else ""
            out.append(self.be.Bind(combo, action, arg))
        s.binds = out


class LuaPage(QWidget):
    """One page per Lua-configured WM; subclasses pick the backend."""

    backend = wasp
    title = ""
    notes: dict[str, str] = {}
    keys_note = ""
    apply_hint = ""

    def __init__(self, path=None):
        super().__init__()
        be = self.backend
        self.cfg = be.Config(path)
        lay = QVBoxLayout(self)
        state = ("" if self.cfg.existed else
                 f" <i>(will be created from {be.EXAMPLE})</i>")
        lay.addWidget(QLabel(f"<b>{self.title}</b> — {self.cfg.path}{state}<br>"
                             f"<small>Your changes go to {self.cfg.overrides_path.name}; "
                             "config.lua only gets one line that loads it. Bold settings "
                             "differ from config.lua.</small>"))
        self.tabs = QTabWidget()
        self.parts = [(name, SpecTab(specs, self.notes.get(name, "")))
                      for name, specs in be.SPECS.items()]
        self.parts.append(("Keybindings", KeysTab(self)))
        for name, w in self.parts:
            self.tabs.addTab(w, name)
        lay.addWidget(self.tabs)
        self.reload()

    def modkey(self) -> str:
        for _, w in self.parts:
            if isinstance(w, SpecTab):
                for f in w.fields:
                    if f.spec.path == ("modkey",):
                        return f.get()
        return ""

    def reload(self) -> None:
        be = self.backend
        self.cfg = be.Config(self.cfg.path)
        try:
            s = self.cfg.read()
        except LuaError as e:
            QMessageBox.critical(self, f"Can't read {self.title}'s config", str(e))
            s = be.Settings()
            for spec in be.ALL_SPECS:
                s.base[spec.path] = s.values[spec.path] = spec.default
            self.setEnabled(False)
        for _, w in self.parts:
            w.load(s)
        self._settings = s

    def collect(self):
        s = self.backend.Settings(base=dict(self._settings.base),
                                  base_binds=self._settings.base_binds)
        for _, w in self.parts:
            w.store(s)
        return s

    def save(self, apply: bool) -> str | None:
        be = self.backend
        s = self.collect()
        errs = be.validate(s)
        if errs:
            QMessageBox.warning(self, "Please fix these first",
                                "\n".join(f"• {e}" for e in errs))
            return None
        try:
            backup = self.cfg.save(s)
        except LuaError as e:
            QMessageBox.critical(self, "Not saved",
                                 f"{self.title}'s config doesn't load with these settings, "
                                 f"so nothing was changed:\n\n{e}")
            return None
        msg = be.reload_running() if apply else "Saved."
        if backup:
            msg += f" (config.lua before Kantele's loader line: {backup.name}.)"
        return msg


class WaspPage(LuaPage):
    backend = wasp
    title = "wasp"
    notes = WASP_NOTES
    keys_note = ("Your keybindings. They are checked before config.lua's, so the same key "
                 "here replaces config.lua's binding; the action \"none\" switches it off. "
                 "Keys look like mod+shift+Return; mod is the Mod key from the Keyboard tab.")


class SpitfirePage(LuaPage):
    backend = spitfire
    title = "spitfire"
    notes = {
        "Windows": "Output scale is a starting value; Mod4+Shift+P/M still rescale live.",
        "Effects": "Blur only applies to windows with a blur = true rule in config.lua.",
    }
    keys_note = ("Your keybindings replace config.lua's binding for the same key "
                 "(spitfire 0.5.5 or newer; older releases keep config.lua's); the action "
                 "\"none\" switches it off. Keys look like Mod4+Shift+Return: Mod4 = Super, "
                 "Mod1 = Alt. config.lua's bindings are Lua functions, shown by the line "
                 "that defines them.")
