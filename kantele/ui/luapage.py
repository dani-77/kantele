"""Settings pages for the Lua-configured WMs (wasp, spitfire)."""

from __future__ import annotations

import shlex

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import shellctl
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


class ShellTab(QWidget):
    """Picks the desktop shell for this compositor. The switch itself, and going
    back if it isn't confirmed, belong to kantele-shell, so they survive this
    window closing."""

    def __init__(self, page: "LuaPage"):
        super().__init__()
        self.page = page
        self.wm = page.backend.NAME
        self.process: QProcess | None = None
        lay = QVBoxLayout(self)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(lambda _: self._update_buttons())
        form = QFormLayout()
        form.addRow("Shell:", self.combo)
        lay.addLayout(form)

        self.state = QLabel()
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #d95c5c; font-weight: bold;")
        lay.addWidget(self.warning)

        row = QHBoxLayout()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self.install)
        row.addWidget(self.install_button)
        self.apply_button = QPushButton("Apply now")
        self.apply_button.clicked.connect(self.apply_now)
        self.next_button = QPushButton("Use from next login")
        self.next_button.clicked.connect(self.use_next_login)
        self.back_button = QPushButton("Back to previous shell")
        self.back_button.clicked.connect(lambda: self.run(["restore"], self.finished))
        for button in (self.apply_button, self.next_button, self.back_button):
            row.addWidget(button)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(_note(
            "With nothing chosen here, the compositor keeps what it came with. Applying "
            "stops the current shell and turns the built-in bar off. If you don't confirm "
            f"within {shellctl.KEEP_SECONDS} seconds, the previous shell comes back."))
        lay.addStretch()

    # The tab keeps no settings of its own in kantele.lua's editable values.
    def load(self, _settings) -> None:
        self.refresh()

    def store(self, _settings) -> None:
        pass

    def _fill_combo(self, selected: str) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(f"What {self.wm} came with", "")
        for name, label in shellctl.SHELLS.items():
            ok = shellctl.installed(name)
            self.combo.addItem(label if ok else f"{label} (not installed)", name)
        self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))
        self.combo.blockSignals(False)

    def _update_buttons(self) -> None:
        shell = self.selected()
        missing = bool(shell) and not shellctl.installed(shell)
        self.install_button.setVisible(missing)
        self.next_button.setEnabled(not missing)
        self.apply_button.setEnabled(not missing and shellctl.is_running_session(self.wm))

    def refresh(self) -> None:
        here = shellctl.is_running_session(self.wm)
        status = shellctl.status() if here else {}
        chosen = shellctl.chosen(self.wm)
        self._fill_combo(chosen)

        running = status.get("running", "")
        parts = [f"Chosen: {shellctl.SHELLS.get(chosen, 'nothing')}."]
        if here:
            parts.insert(0, f"Running now: {shellctl.SHELLS.get(running, 'none')}.")
        else:
            parts.append(f"You're not in a {self.wm} session, so this takes effect at its "
                         "next login.")
        self.state.setText(" ".join(parts))

        self._update_buttons()
        self.back_button.setEnabled(here and bool(status.get("previous")))
        self.warning.setText(self.CONFIG_WARNING if self._config_starts_a_shell() else "")

    CONFIG_WARNING = ("config.lua also starts a shell by itself. Remove that entry, or it "
                      "will run instead of the one chosen here.")

    def _config_starts_a_shell(self) -> bool:
        return shellctl.config_starts_a_shell(self.page.cfg.path)

    def install(self) -> None:
        shell = self.selected()
        try:
            argv = shellctl.install_command(shell)
        except shellctl.CantInstall as e:
            QMessageBox.information(self, "Can't install from here", str(e))
            return
        self.run_command(argv, self._installed)

    def _installed(self, code: int, process: QProcess) -> None:
        self.setEnabled(True)
        selected = self.selected()
        if not shellctl.installed(selected):
            error = bytes(process.readAllStandardError()).decode(errors="replace").strip()
            QMessageBox.warning(self, "Not installed",
                                error or "The shell doesn't look installed.")
        self.refresh()
        self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))

    def selected(self) -> str:
        return self.combo.currentData() or ""

    def _saved_first(self) -> bool:
        # kantele-shell rewrites kantele.lua, and that would lose edits on other tabs.
        return self.page.save(False) is not None

    def use_next_login(self) -> None:
        if not self._saved_first():
            return
        try:
            shellctl.choose(self.wm, self.selected())
        except (LuaError, OSError) as e:
            QMessageBox.critical(self, "Not saved", str(e))
        self.page.reload()

    def apply_now(self) -> None:
        shell = self.selected()
        if not shell:
            self.use_next_login()
            return
        if self._config_starts_a_shell():
            go_on = QMessageBox.warning(
                self, "config.lua starts a shell", self.CONFIG_WARNING + "\n\nApply anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if go_on != QMessageBox.StandardButton.Yes:
                return
        if self._saved_first():
            self.run(["switch", shell], self.confirm)

    def run(self, args: list[str], done) -> None:
        self.run_command([shellctl.command(), *args], done)

    def run_command(self, argv: list[str], done) -> None:
        self.setEnabled(False)
        self.state.setText("Working…")
        process = QProcess(self)
        process.finished.connect(lambda code, _status: done(code, process))
        process.errorOccurred.connect(lambda _error: self.setEnabled(True))
        process.start(argv[0], argv[1:])
        self.process = process

    def finished(self, code: int, process: QProcess) -> None:
        self.setEnabled(True)
        if code != 0:
            error = bytes(process.readAllStandardError()).decode(errors="replace").strip()
            QMessageBox.warning(self, "Shell not changed", error or "kantele-shell failed.")
        self.page.reload()

    def confirm(self, code: int, process: QProcess) -> None:
        if code != 0:
            self.finished(code, process)
            return
        self.setEnabled(True)
        self.page.reload()
        if ask_to_keep(self):
            self.run(["keep"], self.finished)
        else:
            self.run(["restore"], self.finished)


def ask_to_keep(parent: QWidget) -> bool:
    """Runs out shortly before kantele-shell goes back by itself, which still happens
    if this window is gone by then."""
    box = QMessageBox(parent)
    box.setWindowTitle("Keep this shell?")
    keep = box.addButton("Keep", QMessageBox.ButtonRole.AcceptRole)
    back = box.addButton("Go back", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    left = [shellctl.KEEP_SECONDS - 1]

    def tick() -> None:
        box.setText(f"Keep this shell? Going back in {left[0]} seconds.")
        left[0] -= 1
        if left[0] < 0:
            back.click()

    timer = QTimer(box)
    timer.timeout.connect(tick)
    tick()
    timer.start(1000)
    box.exec()
    timer.stop()
    return box.clickedButton() is keep


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
        self.parts.append(("Shell", ShellTab(self)))
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
                                  base_binds=self._settings.base_binds,
                                  shell_autostart=self._settings.shell_autostart)
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
