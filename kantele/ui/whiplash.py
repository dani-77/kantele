"""Settings page for whiplash: config.toml, edited in place like pwm's."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QSpinBox, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from ..backends import whiplash as wl
from .luapage import ShellTab
from .widgets import ColorButton, EditableTable, KeyCaptureDialog


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: palette(placeholder-text);")
    return lbl


def _combo(items, current: str = "") -> QComboBox:
    cb = QComboBox()
    for it in items:
        cb.addItem(it, it)
    if current and cb.findData(current) < 0:
        cb.addItem(current, current)
    if current:
        cb.setCurrentIndex(cb.findData(current))
    return cb


def _action_combo(current: str) -> QComboBox:
    cb = QComboBox()
    for a, (desc, _) in wl.ACTIONS.items():
        cb.addItem(f"{a} — {desc}", a)
    idx = cb.findData(current)
    if idx < 0:
        cb.addItem(current, current)
        idx = cb.count() - 1
    cb.setCurrentIndex(idx)
    return cb


def _link_arg(cb: QComboBox, argedit: QLineEdit) -> None:
    """Enables the argument field only for actions that take one."""
    def sync(_=None):
        kind = wl.ACTIONS.get(cb.currentData(), ("", None))[1]
        argedit.setEnabled(kind is not None)
        argedit.setPlaceholderText(wl.HINTS.get(kind, ""))
    cb.currentIndexChanged.connect(sync)
    sync()


def _optional_float(lo: float, hi: float, value: float | None) -> QDoubleSpinBox:
    """A spin box whose lowest step means "not set"."""
    sp = QDoubleSpinBox()
    sp.setDecimals(2)
    sp.setSingleStep(0.05)
    sp.setRange(lo - 0.01, hi)
    sp.setSpecialValueText("default")
    sp.setValue(value if value is not None else sp.minimum())
    return sp


def _float_or_none(sp: QDoubleSpinBox) -> float | None:
    return None if sp.value() <= sp.minimum() else round(sp.value(), 2)


class WindowsTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.terminal = QLineEdit()
        form.addRow("Terminal:", self.terminal)
        self.mod = _combo(wl.MOD_CHOICES)
        form.addRow("Mod key:", self.mod)
        self.gaps = QSpinBox()
        self.gaps.setRange(0, 200)
        form.addRow("Gaps (px):", self.gaps)
        self.workspaces = QSpinBox()
        self.workspaces.setRange(1, 9)
        form.addRow("Workspaces:", self.workspaces)
        self.layouts = QLineEdit()
        self.layouts.setPlaceholderText("tall, wide, full")
        form.addRow("Layouts, in Mod+space order:", self.layouts)
        self.ffm = QCheckBox("Focus follows the mouse (hovering focuses, clicking raises)")
        form.addRow("", self.ffm)
        self.bwidth = QSpinBox()
        self.bwidth.setRange(0, 50)
        form.addRow("Border width (px):", self.bwidth)
        self.focused = ColorButton()
        form.addRow("Focused border:", self.focused)
        self.normal = ColorButton()
        form.addRow("Other borders:", self.normal)
        lay.addLayout(form)
        lay.addWidget(_note("Changing the number of workspaces needs a new login; "
                            "everything else applies as soon as you save."))
        lay.addStretch()

    def load(self, s: wl.Settings) -> None:
        g = s.general
        self.terminal.setText(str(g["terminal"]))
        mod = str(g["mod"])
        mod = wl.MODS.get(mod.lower(), mod)
        if self.mod.findData(mod) < 0:
            self.mod.addItem(mod, mod)
        self.mod.setCurrentIndex(self.mod.findData(mod))
        self.gaps.setValue(int(g["gaps"]))
        self.workspaces.setValue(int(g["workspaces"]))
        self.layouts.setText(", ".join(str(l) for l in g["layouts"]))
        self.ffm.setChecked(bool(g["focus_follows_mouse"]))
        self.bwidth.setValue(int(s.border["width"]))
        self.focused.set_color(str(s.border["focused"]))
        self.normal.set_color(str(s.border["normal"]))

    def store(self, s: wl.Settings) -> None:
        g = s.general
        g["terminal"] = self.terminal.text().strip()
        # Keep the file's own spelling ("alt", "Alt") when the key didn't change.
        if wl.MODS.get(str(g["mod"]).lower()) != self.mod.currentData():
            g["mod"] = self.mod.currentData()
        g["gaps"] = self.gaps.value()
        g["workspaces"] = self.workspaces.value()
        g["layouts"] = [l.strip() for l in self.layouts.text().split(",") if l.strip()]
        g["focus_follows_mouse"] = self.ffm.isChecked()
        s.border["width"] = self.bwidth.value()
        s.border["focused"] = self.focused.color()
        s.border["normal"] = self.normal.color()


class KeyboardTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edits = {}
        for k, label in (("layout", "Layout (e.g. pt, us)"), ("variant", "Variant"),
                         ("options", "Options (e.g. caps:escape)")):
            self.edits[k] = QLineEdit()
            form.addRow(label + ":", self.edits[k])
        self.rate = QSpinBox()
        self.rate.setRange(1, 255)
        form.addRow("Repeat rate (per second):", self.rate)
        self.delay = QSpinBox()
        self.delay.setRange(1, 10000)
        form.addRow("Repeat delay (ms):", self.delay)
        lay.addLayout(form)
        lay.addWidget(_note("Several layouts and options are separated by commas, e.g. pt,us "
                            "and grp:alt_shift_toggle. Applies to physical keyboards."))
        lay.addStretch()

    def load(self, s: wl.Settings) -> None:
        for k, e in self.edits.items():
            e.setText(str(s.keyboard[k]))
        self.rate.setValue(int(s.keyboard["repeat_rate"]))
        self.delay.setValue(int(s.keyboard["repeat_delay"]))

    def store(self, s: wl.Settings) -> None:
        for k, e in self.edits.items():
            s.keyboard[k] = ",".join(p.strip() for p in e.text().split(","))
        s.keyboard["repeat_rate"] = self.rate.value()
        s.keyboard["repeat_delay"] = self.delay.value()


class TouchpadTab(QWidget):
    LABELS = {"tap": "Tap to click (1/2/3 fingers = left/right/middle)",
              "tap_and_drag": "Tap, then touch again and move to drag",
              "drag_lock": "A drag survives lifting the finger briefly",
              "natural_scroll": "Natural scrolling",
              "disable_while_typing": "Disable while typing"}

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.checks = {k: QCheckBox(v) for k, v in self.LABELS.items()}
        for c in self.checks.values():
            form.addRow("", c)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(-1, 1)
        self.speed.setSingleStep(0.1)
        form.addRow("Pointer speed (-1 slow .. 1 fast):", self.speed)
        self.profile = _combo(wl.ACCEL_PROFILES)
        form.addRow("Acceleration:", self.profile)
        self.click = _combo(wl.CLICK_METHODS)
        form.addRow("Click method:", self.click)
        lay.addLayout(form)
        lay.addWidget(_note("Only touchpads are affected; mice keep libinput's defaults."))
        lay.addStretch()

    def load(self, s: wl.Settings) -> None:
        for k, c in self.checks.items():
            c.setChecked(bool(s.touchpad[k]))
        self.speed.setValue(float(s.touchpad["speed"]))
        self.profile.setCurrentIndex(self.profile.findData(s.touchpad["accel_profile"]))
        self.click.setCurrentIndex(self.click.findData(s.touchpad["click_method"]))

    def store(self, s: wl.Settings) -> None:
        for k, c in self.checks.items():
            s.touchpad[k] = c.isChecked()
        speed = round(self.speed.value(), 2)
        # The file's 0 and 0.0 are the same speed; keep whichever it has.
        if speed != s.touchpad["speed"]:
            s.touchpad["speed"] = speed
        s.touchpad["accel_profile"] = self.profile.currentData()
        s.touchpad["click_method"] = self.click.currentData()


class RulesTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note("What to do with a new window, by its app id (Wayland) or class "
                            "(X11), ignoring case. whiplash writes every new window's app id "
                            "to ~/.local/state/whiplash/whiplash.log."))
        self.et = EditableTable(["App id", "Workspace", "Floating"], self._add)
        lay.addWidget(self.et, 1)

    def _add(self, app: str = "", ws: int | None = None, floating: bool | None = None) -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        t.setCellWidget(r, 0, QLineEdit(app))
        wcb = QComboBox()
        wcb.addItem("—", None)
        for n in range(1, 10):
            wcb.addItem(str(n), n)
        wcb.setCurrentIndex(max(0, wcb.findData(ws)) if ws is not None else 0)
        t.setCellWidget(r, 1, wcb)
        fcb = QComboBox()
        for label, v in (("—", None), ("float", True), ("tile, even dialogs", False)):
            fcb.addItem(label, v)
        fcb.setCurrentIndex({None: 0, True: 1, False: 2}[floating])
        t.setCellWidget(r, 2, fcb)

    def load(self, s: wl.Settings) -> None:
        self.et.table.setRowCount(0)
        for r in s.rules:
            self._add(r.app_id, r.workspace, r.floating)

    def store(self, s: wl.Settings) -> None:
        t = self.et.table
        s.rules = [wl.Rule(t.cellWidget(r, 0).text().strip(), t.cellWidget(r, 1).currentData(),
                           t.cellWidget(r, 2).currentData())
                   for r in range(t.rowCount())]


class ScratchpadsTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note("A floating window one key shows and hides without closing it. "
                            "The first toggle runs the command; the window it opens is caught "
                            "by its app id (empty: the name). Bind it on the Keybindings tab "
                            "with the action toggle-scratchpad and the name."))
        self.et = EditableTable(["Name", "Command", "App id", "Width", "Height"], self._add)
        lay.addWidget(self.et, 1)

    def _add(self, name: str = "", command: str = "", app: str = "",
             width: float | None = None, height: float | None = None) -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        t.setCellWidget(r, 0, QLineEdit(name))
        t.setCellWidget(r, 1, QLineEdit(command))
        t.setCellWidget(r, 2, QLineEdit(app))
        t.setCellWidget(r, 3, _optional_float(0.1, 1, width))
        t.setCellWidget(r, 4, _optional_float(0.1, 1, height))

    def load(self, s: wl.Settings) -> None:
        self.et.table.setRowCount(0)
        for p in s.scratchpads:
            self._add(p.name, p.command, p.app_id, p.width, p.height)

    def store(self, s: wl.Settings) -> None:
        t = self.et.table
        s.scratchpads = [wl.Scratchpad(t.cellWidget(r, 0).text().strip(),
                                       t.cellWidget(r, 1).text().strip(),
                                       t.cellWidget(r, 2).text().strip(),
                                       _float_or_none(t.cellWidget(r, 3)),
                                       _float_or_none(t.cellWidget(r, 4)))
                         for r in range(t.rowCount())]


class GesturesTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note("Touchpad swipes, with any action a key can have. Swipes with a "
                            "finger count used here are whiplash's; the others, and pinch "
                            "zoom, still reach the app under the pointer."))
        self.et = EditableTable(["Fingers", "Direction", "Action", "Argument"], self._add)
        hh = self.et.table.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.et, 1)

    def _add(self, fingers: int = 3, direction: str = "left", action: str = "workspace-prev",
             arg: str = "") -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        fcb = QComboBox()
        for n in (3, 4, 5):
            fcb.addItem(str(n), n)
        fcb.setCurrentIndex(max(0, fcb.findData(fingers)))
        t.setCellWidget(r, 0, fcb)
        t.setCellWidget(r, 1, _combo(wl.DIRECTIONS, direction))
        cb = _action_combo(action)
        argedit = QLineEdit(arg)
        t.setCellWidget(r, 2, cb)
        t.setCellWidget(r, 3, argedit)
        _link_arg(cb, argedit)

    def load(self, s: wl.Settings) -> None:
        self.et.table.setRowCount(0)
        for g in s.gestures:
            self._add(g.fingers, g.direction, g.action, g.arg)

    def store(self, s: wl.Settings) -> None:
        t = self.et.table
        out = []
        for r in range(t.rowCount()):
            argw = t.cellWidget(r, 3)
            out.append(wl.Gesture(t.cellWidget(r, 0).currentData(), t.cellWidget(r, 1).currentData(),
                                  t.cellWidget(r, 2).currentData(),
                                  argw.text().strip() if argw.isEnabled() else ""))
        s.gestures = out


class OutputsTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note("Scale and position per monitor, by connector name (wlr-randr "
                            "lists them, e.g. eDP-1, HDMI-A-1). Monitors not listed get "
                            "scale 1 and sit left to right."))
        self.et = EditableTable(["Connector", "Scale", "Position (x, y)"], self._add)
        lay.addWidget(self.et, 1)

    def _add(self, name: str = "", scale: float | None = None,
             position: tuple[int, int] | None = None) -> None:
        t = self.et.table
        r = t.rowCount()
        t.insertRow(r)
        t.setCellWidget(r, 0, QLineEdit(name))
        t.setCellWidget(r, 1, _optional_float(0.5, 4, scale))
        pos = QLineEdit(f"{position[0]}, {position[1]}" if position else "")
        pos.setPlaceholderText("automatic")
        t.setCellWidget(r, 2, pos)

    def load(self, s: wl.Settings) -> None:
        self.et.table.setRowCount(0)
        for o in s.outputs:
            self._add(o.name, o.scale, o.position)

    def store(self, s: wl.Settings) -> None:
        t = self.et.table
        out = []
        for r in range(t.rowCount()):
            text = t.cellWidget(r, 2).text().replace(" ", "")
            try:
                x, y = (int(v) for v in text.split(",")) if text else (None, None)
                position = (x, y) if text else None
            except ValueError:
                position = None
            out.append(wl.Output(t.cellWidget(r, 0).text().strip(),
                                 _float_or_none(t.cellWidget(r, 1)), position))
        s.outputs = out


class KeysTab(QWidget):
    def __init__(self, page: "WhiplashPage"):
        super().__init__()
        self.page = page
        lay = QVBoxLayout(self)
        self.state = _note("")
        lay.addWidget(self.state)
        self.et = EditableTable(["Key", "Action", "Argument"], self._add)
        hh = self.et.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.et.table.setColumnWidth(0, 230)
        lay.addWidget(self.et, 1)
        self.from_file = False
        self.loaded: list[wl.Bind] = []

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
        cb = _action_combo(action)
        argedit = QLineEdit(arg)
        t.setCellWidget(r, 1, cb)
        t.setCellWidget(r, 2, argedit)
        _link_arg(cb, argedit)
        t.resizeRowsToContents()

    def _capture(self, edit: QLineEdit) -> None:
        d = KeyCaptureDialog(self)
        if d.exec() and d.result_key:
            edit.setText(wl.combo_from_penrose(d.result_key, self.page.modkey()))

    def _rows(self) -> list[wl.Bind]:
        t = self.et.table
        out = []
        for r in range(t.rowCount()):
            argw = t.cellWidget(r, 2)
            out.append(wl.Bind(t.cellWidget(r, 0).findChild(QLineEdit).text().strip(),
                               t.cellWidget(r, 1).currentData(),
                               argw.text().strip() if argw.isEnabled() else ""))
        return out

    def load(self, s: wl.Settings) -> None:
        self.from_file = s.binds is not None
        self.loaded = s.effective_binds()
        self.state.setText(
            "Every key whiplash answers to. The [keybinds] table replaces whiplash's "
            "built-in set, so this list is the whole keymap. Keys look like Mod+Shift+Return; "
            "Mod is the Mod key from the Windows tab, letters are lower case."
            + ("" if self.from_file else
               " Your config.toml has no [keybinds] yet, so these are whiplash's built-in "
               "keys; the first change writes them all to the file."))
        self.et.table.setRowCount(0)
        for b in self.loaded:
            self._add(b.combo, b.action, b.arg)

    def store(self, s: wl.Settings) -> None:
        rows = self._rows()
        # Untouched built-in keys stay out of the file.
        s.binds = rows if self.from_file or rows != self.loaded else None


class WhiplashPage(QWidget):
    backend = wl
    title = "whiplash"

    def __init__(self, path=None):
        super().__init__()
        self.cfg = wl.Config(path)
        lay = QVBoxLayout(self)
        state = "" if self.cfg.existed else f" <i>(will be created from {wl.EXAMPLE})</i>"
        lay.addWidget(QLabel(f"<b>whiplash</b> — {self.cfg.path}{state}<br>"
                             "<small>Edited in place: your comments stay. whiplash reloads "
                             "the file as soon as it is saved.</small>"))
        self.tabs = QTabWidget()
        self.windows = WindowsTab()
        self.parts = [
            ("Windows", self.windows), ("Keyboard", KeyboardTab()), ("Touchpad", TouchpadTab()),
            ("Rules", RulesTab()), ("Scratchpads", ScratchpadsTab()), ("Gestures", GesturesTab()),
            ("Monitors", OutputsTab()), ("Keybindings", KeysTab(self)), ("Shell", ShellTab(self)),
        ]
        for name, w in self.parts:
            self.tabs.addTab(w, name)
        lay.addWidget(self.tabs)
        self.reload()

    def modkey(self) -> str:
        return self.windows.mod.currentData() or "Alt"

    def reload(self) -> None:
        self.cfg = wl.Config(self.cfg.path)
        s = self.cfg.read()
        for _, w in self.parts:
            w.load(s)

    def collect(self) -> wl.Settings:
        s = self.cfg.read()
        for _, w in self.parts:
            w.store(s)
        return s

    def save(self, apply: bool) -> str | None:
        s = self.collect()
        errs = wl.validate(s)
        if errs:
            QMessageBox.warning(self, "Please fix these first",
                                "\n".join(f"• {e}" for e in errs))
            return None
        backup = self.cfg.save(s)
        msg = wl.reload_running()
        if backup:
            msg += f" (Your original file was kept as {backup.name}.)"
        return msg
