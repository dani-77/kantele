"""whiplash backend: reads, validates and writes ~/.config/whiplash/config.toml.

whiplash's config is declarative TOML laid over the defaults compiled into
whiplash (app/Main.hs), so, as with pwm, the file is edited in place with
tomlkit: comments and layout stay, and a save without changes leaves it byte
for byte identical. TOML has no include, so unlike wasp and spitfire there is
no generated side file: Kantele owns nothing but the keys it changes.

Two whiplash rules shape this module:
- A [keybinds] table replaces the whole built-in key set, so the file always
  lists every active binding. Without the table the built-in keys apply; the
  first edit writes the full set (never one key alone, which would drop all
  the others).
- whiplash reloads the file by itself whenever it is written, and keeps the
  old config (with a notification) when the new one has an error. validate()
  mirrors whiplash's own checks (src/Whiplash/Settings.hs) so a save never
  gets there.

The defaults below mirror whiplash 0.2's app/Main.hs; keep them in sync.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from tomlkit.items import Array, InlineTable, Table

from .pwm import _plain, _set, _table

NAME = "whiplash"
EXAMPLE = Path("/usr/share/whiplash/config.toml")
# The files `kantele shell-keys` backs up before changing them.
SHELL_FILES = ("config.toml",)
# whiplash has no bar of its own for kantele-shell to turn on or off.
HAS_BAR = False
SHELL_START = "kantele-shell start"

LAYOUTS = ("tall", "wide", "full")
MODS = {"alt": "Alt", "mod1": "Alt", "super": "Super", "logo": "Super", "win": "Super",
        "mod4": "Super", "ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift"}
MOD_CHOICES = ("Alt", "Super", "Ctrl", "Shift")
DIRECTIONS = ("left", "right", "up", "down")
ACCEL_PROFILES = ("default", "adaptive", "flat")
CLICK_METHODS = ("default", "button-areas", "clickfinger")

# Top-level settings shown in the GUI, with whiplash's built-in values.
GENERAL_DEFAULTS: dict[str, object] = {
    "terminal": "alacritty",
    "mod": "Alt",
    "gaps": 4,
    "workspaces": 9,
    "layouts": list(LAYOUTS),
    "focus_follows_mouse": False,
}
BORDER_DEFAULTS: dict[str, object] = {"width": 2, "focused": "#aa96da", "normal": "#3b3b4f"}
KEYBOARD_DEFAULTS: dict[str, object] = {
    "layout": "pt", "variant": "", "options": "", "repeat_rate": 25, "repeat_delay": 600}
TOUCHPAD_BOOLS = ("tap", "tap_and_drag", "drag_lock", "natural_scroll", "disable_while_typing")
TOUCHPAD_DEFAULTS: dict[str, object] = {
    "tap": True, "tap_and_drag": True, "drag_lock": True, "natural_scroll": False,
    "disable_while_typing": True, "speed": 0.0, "accel_profile": "default",
    "click_method": "default"}

# action -> (description, argument kind). Kinds: None, "command", "workspace",
# "layout", "ratio", "screen", "scratchpad". Mirrors actionNames in Settings.hs.
ACTIONS: dict[str, tuple[str, str | None]] = {
    "spawn": ("Run a command", "command"),
    "terminal": ("Open the terminal", None),
    "close": ("Close focused window", None),
    "quit": ("Quit whiplash", None),
    "reload": ("Reload config.toml", None),
    "focus-down": ("Focus next window", None),
    "focus-up": ("Focus previous window", None),
    "swap-down": ("Move window down the stack", None),
    "swap-up": ("Move window up the stack", None),
    "swap-master": ("Swap with the master window", None),
    "workspace": ("Go to workspace", "workspace"),
    "move-to-workspace": ("Move window to workspace", "workspace"),
    "workspace-previous": ("Back to the previous workspace", None),
    "workspace-next": ("Next workspace (wraps)", None),
    "workspace-prev": ("Previous workspace (wraps)", None),
    "layout": ("Switch to a layout", "layout"),
    "next-layout": ("Next layout", None),
    "master-ratio": ("Grow/shrink the master area", "ratio"),
    "toggle-float": ("Float / tile the window", None),
    "fullscreen": ("Toggle fullscreen", None),
    "focus-screen": ("Focus next/previous screen", "screen"),
    "move-to-screen": ("Move window to next/previous screen", "screen"),
    "toggle-scratchpad": ("Show / hide a scratchpad", "scratchpad"),
}
HINTS = {"command": "command to run", "workspace": "1-9", "layout": "tall, wide or full",
         "ratio": "e.g. +0.05 or -0.05", "screen": "next or prev",
         "scratchpad": "scratchpad name"}


@dataclass
class Bind:
    combo: str          # "Mod+Shift+Return"
    action: str         # "spawn"
    arg: str = ""       # "alacritty"


# whiplash's compiled-in keys (app/Main.hs d77Keys), which apply while the file
# has no [keybinds] table.
DEFAULT_BINDS: list[Bind] = [
    Bind("Mod+Shift+Return", "terminal"),
    Bind("Mod+p", "spawn", "wmenu-run"),
    Bind("Super+space", "spawn", "qsd77 -c utumno launcher"),
    Bind("Super+a", "spawn", "qsd77 -c utumno ollama"),
    Bind("Super+t", "spawn", "qsd77 -c utumno locker"),
    Bind("Super+x", "spawn", "qsd77 -c utumno session"),
    Bind("Super+y", "spawn", "qsd77 -c utumno wallpaper"),
    Bind("Super+r", "spawn", "d77run"),
    Bind("XF86AudioRaiseVolume", "spawn", "amixer -q set Master 5%+"),
    Bind("XF86AudioLowerVolume", "spawn", "amixer -q set Master 5%-"),
    Bind("XF86AudioMute", "spawn", "amixer -q set Master toggle"),
    Bind("Print", "spawn", "grim ~/screenshot-$(date +%Y%m%d-%H%M%S).png"),
    Bind("Mod+j", "focus-down"),
    Bind("Mod+k", "focus-up"),
    Bind("Mod+Tab", "workspace-previous"),
    Bind("Mod+Return", "swap-master"),
    Bind("Mod+Shift+j", "swap-down"),
    Bind("Mod+Shift+k", "swap-up"),
    Bind("Mod+h", "master-ratio", "-0.05"),
    Bind("Mod+l", "master-ratio", "+0.05"),
    Bind("Mod+t", "layout", "tall"),
    Bind("Mod+w", "layout", "wide"),
    Bind("Mod+m", "layout", "full"),
    Bind("Mod+space", "next-layout"),
    Bind("Mod+Shift+space", "toggle-float"),
    Bind("Mod+e", "fullscreen"),
    Bind("Mod+Shift+c", "close"),
    Bind("Mod+Shift+q", "quit"),
    *[Bind(f"Mod+{n}", "workspace", str(n)) for n in range(1, 10)],
    *[Bind(f"Mod+Shift+{n}", "move-to-workspace", str(n)) for n in range(1, 10)],
]


@dataclass
class Rule:
    app_id: str
    workspace: int | None = None
    floating: bool | None = None


@dataclass
class Scratchpad:
    name: str
    command: str
    app_id: str = ""            # empty: whiplash uses the name
    width: float | None = None  # None: whiplash's 0.6
    height: float | None = None


@dataclass
class Gesture:
    fingers: int
    direction: str
    action: str
    arg: str = ""

    @property
    def key(self) -> str:
        return f"{self.fingers}-{self.direction}"


@dataclass
class Output:
    name: str
    scale: float | None = None
    position: tuple[int, int] | None = None


@dataclass
class Settings:
    """Everything the GUI edits. general/border/keyboard/touchpad hold full
    values (file value, or whiplash's default); only keys the file already has,
    or values that differ from the default, are written."""

    general: dict[str, object] = field(default_factory=lambda: dict(GENERAL_DEFAULTS))
    border: dict[str, object] = field(default_factory=lambda: dict(BORDER_DEFAULTS))
    autostart: list[str] | None = None
    keyboard: dict[str, object] = field(default_factory=lambda: dict(KEYBOARD_DEFAULTS))
    touchpad: dict[str, object] = field(default_factory=lambda: dict(TOUCHPAD_DEFAULTS))
    rules: list[Rule] = field(default_factory=list)
    scratchpads: list[Scratchpad] = field(default_factory=list)
    gestures: list[Gesture] = field(default_factory=list)
    outputs: list[Output] = field(default_factory=list)
    # None: the file has no [keybinds], so whiplash's built-in keys apply.
    binds: list[Bind] | None = None
    # For `kantele shell-keys`, which compares against the compositor's own
    # keys; in whiplash every binding lives in the one file.
    base_binds: list[Bind] = field(default_factory=list)

    @property
    def shell_autostart(self) -> bool:
        return SHELL_START in (self.autostart or [])

    @shell_autostart.setter
    def shell_autostart(self, on: bool) -> None:
        current = list(self.autostart or [])
        if on and SHELL_START not in current:
            current.append(SHELL_START)
        elif not on:
            current = [c for c in current if c != SHELL_START]
        self.autostart = current

    def effective_binds(self) -> list[Bind]:
        return list(self.binds) if self.binds is not None else [Bind(**vars(b)) for b in DEFAULT_BINDS]


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "whiplash" / "config.toml"


def split_action(text: str) -> tuple[str, str]:
    """"spawn foot -e fish" -> ("spawn", "foot -e fish")."""
    parts = text.strip().split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1].strip() if len(parts) > 1 else ""


def join_action(action: str, arg: str) -> str:
    return f"{action} {arg}".strip()


def normalize_combo(combo: str) -> str:
    """A spelling-independent form, for comparing combos: modifiers in a fixed
    order and case, single letters lower case (whiplash matches unshifted keys)."""
    parts = [p for p in combo.split("+") if p]
    if not parts:
        return ""
    *mods, key = parts
    canon = []
    for m in mods:
        low = m.lower()
        canon.append("Mod" if low == "mod" else MODS.get(low, m))
    order = {"Mod": 0, "Super": 1, "Ctrl": 2, "Alt": 3, "Shift": 4}
    canon = sorted(set(canon), key=lambda m: order.get(m, 9))
    if len(key) == 1:
        key = key.lower()
    return "+".join([*canon, key])


def combo_from_penrose(key: str, modkey: str) -> str:
    """Kantele's key recorder speaks penrose ("M-S-x"); whiplash wants
    "Super+Shift+x", with the configured Mod key written as Mod."""
    *mods, name = key.split("-")
    names = {"M": "Super", "A": "Alt", "C": "Ctrl", "S": "Shift"}
    out = []
    for m in mods:
        n = names.get(m, m)
        out.append("Mod" if n == modkey else n)
    return "+".join([*out, name])


class Config:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config_path()
        self.existed = self.path.exists()
        if self.existed:
            self.doc = tomlkit.parse(self.path.read_text())
        elif EXAMPLE.exists():
            # start from the commented example, as whiplash's own docs suggest
            self.doc = tomlkit.parse(EXAMPLE.read_text())
        else:
            self.doc = tomlkit.document()

    # ── reading ──────────────────────────────────────────────────────────
    def read(self) -> Settings:
        d = self.doc
        s = Settings()
        for k in GENERAL_DEFAULTS:
            if k in d:
                v = _plain(d[k])
                s.general[k] = list(v) if isinstance(v, list) else v
        border = d.get("border", {})
        for k in BORDER_DEFAULTS:
            if k in border:
                s.border[k] = _plain(border[k])
        if "autostart" in d:
            s.autostart = [str(c) for c in d["autostart"]]
        for name, target in (("keyboard", s.keyboard), ("touchpad", s.touchpad)):
            table = d.get(name, {})
            for k in target:
                if k in table:
                    target[k] = _plain(table[k])
        for app, r in d.get("rules", {}).items():
            s.rules.append(Rule(str(app), _plain(r.get("workspace")), _plain(r.get("float"))))
        for name, p in d.get("scratchpads", {}).items():
            s.scratchpads.append(Scratchpad(str(name), str(p.get("command", "")),
                                            str(p.get("app_id", "")),
                                            _plain(p.get("width")), _plain(p.get("height"))))
        for key, value in d.get("gestures", {}).items():
            fingers, _, direction = str(key).partition("-")
            action, arg = split_action(str(value))
            s.gestures.append(Gesture(int(fingers) if fingers.isdigit() else 0,
                                      direction, action, arg))
        for name, o in d.get("outputs", {}).items():
            pos = o.get("position")
            s.outputs.append(Output(str(name), _plain(o.get("scale")),
                                    tuple(int(v) for v in pos) if pos is not None else None))
        if isinstance(d.get("keybinds"), Table):
            s.binds = []
            for combo, value in d["keybinds"].items():
                action, arg = split_action(str(value))
                s.binds.append(Bind(str(combo), action, arg))
        return s

    # ── writing ──────────────────────────────────────────────────────────
    def apply(self, s: Settings) -> None:
        """Writes `s` into the document, editing only what changed."""
        d = self.doc
        for k, default in GENERAL_DEFAULTS.items():
            _set_default_aware(d, k, s.general.get(k), default)

        border = d.get("border")
        if isinstance(border, (Table, InlineTable)):
            for k in BORDER_DEFAULTS:
                _set(border, k, s.border.get(k))
        elif s.border != BORDER_DEFAULTS:
            d["border"] = tomlkit.inline_table()
            d["border"].update(s.border)

        if s.autostart is not None:
            _set_list(d, "autostart", s.autostart)

        for name, values, defaults in (("keyboard", s.keyboard, KEYBOARD_DEFAULTS),
                                       ("touchpad", s.touchpad, TOUCHPAD_DEFAULTS)):
            existing = d.get(name)
            if isinstance(existing, Table):
                for k in defaults:
                    _set_default_aware(existing, k, values.get(k), defaults[k])
            elif values != defaults:
                t = _table(d, name)
                for k in defaults:
                    _set_default_aware(t, k, values.get(k), defaults[k])

        _set_named(d, "rules", {r.app_id: {"workspace": r.workspace, "float": r.floating}
                                for r in s.rules})
        _set_named(d, "scratchpads", {p.name: {"command": p.command, "app_id": p.app_id or None,
                                               "width": p.width, "height": p.height}
                                      for p in s.scratchpads})
        _set_named(d, "outputs", {o.name: {"scale": o.scale,
                                           "position": list(o.position) if o.position else None}
                                  for o in s.outputs})
        _set_flat(d, "gestures", {g.key: join_action(g.action, g.arg) for g in s.gestures})
        if s.binds is not None:
            _set_flat(d, "keybinds", {b.combo: join_action(b.action, b.arg) for b in s.binds},
                      keep_empty=True)

    def save(self, s: Settings | None = None) -> Path | None:
        """Applies `s` (if given) and writes the file atomically. The first time
        Kantele touches an existing config it keeps a copy next to it; returns
        that path. whiplash notices the write and reloads by itself."""
        if s is not None:
            self.apply(s)
        backup = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.existed:
            bak = self.path.with_name(self.path.name + ".kantele-bak")
            if not bak.exists():
                shutil.copy2(self.path, bak)
                backup = bak
        tmp = self.path.with_name(self.path.name + ".kantele-tmp")
        tmp.write_text(tomlkit.dumps(self.doc))
        os.replace(tmp, self.path)
        self.existed = True
        return backup


# ── validation: whiplash's own rules (Settings.hs) ───────────────────────
COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
KEY_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def check_combo(combo: str) -> str | None:
    parts = combo.split("+")
    if not combo or any(not p for p in parts):
        return f"Key '{combo}' is not a key combination (e.g. Mod+Shift+Return)."
    *mods, key = parts
    for m in mods:
        if m.lower() != "mod" and m.lower() not in MODS:
            return f"Key '{combo}': unknown modifier '{m}' (Mod, Alt, Super, Ctrl, Shift)."
    if len(key) == 1:
        if ord(key) >= 0x7f:
            return f"Key '{combo}': write '{key}' by its key name."
    elif not KEY_NAME_RE.match(key):
        return f"Key '{combo}': '{key}' is not a key name."
    return None


def check_action(action: str, arg: str, s: Settings) -> str | None:
    if action not in ACTIONS:
        return f"unknown action '{action}'"
    kind = ACTIONS[action][1]
    tags = range(1, int(s.general.get("workspaces", 9)) + 1)
    if kind is None:
        return f"{action} takes no argument" if arg else None
    if kind == "command":
        return None if arg else "spawn needs a command"
    if kind == "workspace":
        return None if arg.isdigit() and int(arg) in tags else f"no workspace '{arg}'"
    if kind == "layout":
        if arg.lower() not in [str(l).lower() for l in s.general.get("layouts", LAYOUTS)]:
            return f"layout '{arg}' is not in the layouts list"
        return None
    if kind == "ratio":
        try:
            ok = abs(float(arg.lstrip("+"))) < 1
        except ValueError:
            ok = False
        return None if ok else "master-ratio wants a step like +0.05 or -0.05"
    if kind == "screen":
        return None if arg.lower() in ("next", "prev", "previous") else "expected next or prev"
    if kind == "scratchpad":
        return None if arg in [p.name for p in s.scratchpads] else f"no scratchpad '{arg}'"
    return None


def validate(s: Settings) -> list[str]:
    """Problems whiplash would reject, as readable messages."""
    errs: list[str] = []
    g = s.general
    if not str(g.get("terminal", "")).strip():
        errs.append("The terminal can't be empty.")
    if str(g.get("mod", "")).lower() not in MODS:
        errs.append(f"Mod key '{g.get('mod')}' must be Alt, Super, Ctrl or Shift.")
    gaps = g.get("gaps")
    if not isinstance(gaps, int) or not 0 <= gaps < 100000:
        errs.append("Gaps must be a whole number of pixels.")
    ws = g.get("workspaces")
    if not isinstance(ws, int) or not 1 <= ws <= 9:
        errs.append("Workspaces must be between 1 and 9.")
    layouts = g.get("layouts") or []
    if not layouts:
        errs.append("At least one layout is needed.")
    for l in layouts:
        if str(l).lower() not in LAYOUTS:
            errs.append(f"Unknown layout '{l}' (tall, wide, full).")
    width = s.border.get("width")
    if not isinstance(width, int) or not 0 <= width < 100000:
        errs.append("Border width must be a whole number of pixels.")
    for k in ("focused", "normal"):
        if not COLOR_RE.match(str(s.border.get(k, ""))):
            errs.append(f"Border {k} colour must be #rrggbb or #rrggbbaa.")
    for k in ("repeat_rate", "repeat_delay"):
        v = s.keyboard.get(k)
        if not isinstance(v, int) or not 0 <= v < 100000:
            errs.append(f"Keyboard {k.replace('_', ' ')} must be a whole number.")
    speed = s.touchpad.get("speed")
    if not isinstance(speed, (int, float)) or not -1 <= speed <= 1:
        errs.append("Touchpad speed must be between -1 and 1.")
    if s.touchpad.get("accel_profile") not in ACCEL_PROFILES:
        errs.append("Touchpad acceleration must be default, adaptive or flat.")
    if s.touchpad.get("click_method") not in CLICK_METHODS:
        errs.append("Touchpad click method must be default, button-areas or clickfinger.")

    tags = range(1, (ws if isinstance(ws, int) else 9) + 1)
    seen: set[str] = set()
    for r in s.rules:
        if not r.app_id.strip():
            errs.append("A window rule has no app id.")
        elif r.app_id.lower() in seen:
            errs.append(f"Two window rules for '{r.app_id}'.")
        seen.add(r.app_id.lower())
        if r.workspace is not None and r.workspace not in tags:
            errs.append(f"Window rule '{r.app_id}': no workspace {r.workspace}.")
        if r.workspace is None and r.floating is None:
            errs.append(f"Window rule '{r.app_id}' sets neither a workspace nor floating.")
    names: set[str] = set()
    for p in s.scratchpads:
        if not p.name.strip() or re.search(r"\s", p.name):
            errs.append(f"Scratchpad name '{p.name}' must be one word.")
        elif p.name in names:
            errs.append(f"Two scratchpads named '{p.name}'.")
        names.add(p.name)
        if not p.command.strip():
            errs.append(f"Scratchpad '{p.name}' needs a command.")
        for label, v in (("width", p.width), ("height", p.height)):
            if v is not None and not 0.1 <= v <= 1:
                errs.append(f"Scratchpad '{p.name}': {label} must be between 0.1 and 1.")
    gkeys: set[str] = set()
    for gst in s.gestures:
        if gst.fingers not in (3, 4, 5):
            errs.append(f"Gesture '{gst.key}': swipes use 3 to 5 fingers.")
        if gst.direction not in DIRECTIONS:
            errs.append(f"Gesture '{gst.key}': direction must be left, right, up or down.")
        if gst.key in gkeys:
            errs.append(f"Gesture '{gst.key}' is set twice.")
        gkeys.add(gst.key)
        problem = check_action(gst.action, gst.arg, s)
        if problem:
            errs.append(f"Gesture '{gst.key}': {problem}.")
    onames: set[str] = set()
    for o in s.outputs:
        if not o.name.strip():
            errs.append("An output has no connector name (e.g. eDP-1).")
        elif o.name in onames:
            errs.append(f"Output '{o.name}' is listed twice.")
        onames.add(o.name)
        if o.scale is not None and not 0.5 <= o.scale <= 4:
            errs.append(f"Output '{o.name}': scale must be between 0.5 and 4.")
        if o.scale is None and o.position is None:
            errs.append(f"Output '{o.name}' sets neither a scale nor a position.")
    combos: set[str] = set()
    for b in s.binds or []:
        problem = check_combo(b.combo)
        if problem:
            errs.append(problem)
            continue
        norm = normalize_combo(b.combo)
        if norm in combos:
            errs.append(f"Key '{b.combo}' is bound more than once.")
        combos.add(norm)
        problem = check_action(b.action, b.arg, s)
        if problem:
            errs.append(f"Key '{b.combo}': {problem}.")
    return errs


def reload_running() -> str:
    return "Saved. whiplash reloads config.toml by itself."


# ── tomlkit helpers ──────────────────────────────────────────────────────
def _set_default_aware(table, key: str, value, default) -> None:
    """A key the file has is kept up to date (even back at the default); a key
    it hasn't is only added when the value differs from whiplash's default."""
    if key in table:
        if _plain(table[key]) == value:
            return  # unchanged, even an empty string the file spells out
        if isinstance(_plain(table[key]), list) and isinstance(value, list):
            _set_list(table, key, value)
        else:
            _set(table, key, value)
    elif value is not None and value != default:
        table[key] = value


def _set_list(table, key: str, values: list) -> None:
    """Replaces a list's items in place, so a multi-line array stays multi-line."""
    current = table.get(key)
    if isinstance(current, Array):
        if [_plain(v) for v in current] == list(values):
            return
        while len(current):
            del current[0]
        for v in values:
            current.append(v)
    elif _plain(current) != list(values):
        table[key] = values


def _set_flat(doc, name: str, entries: dict[str, str], keep_empty: bool = False) -> None:
    """A table of "key" = "value" ([keybinds], [gestures]): existing keys keep
    their place and comments, removed ones go, new ones are appended."""
    table = doc.get(name)
    if not isinstance(table, Table):
        if not entries and not keep_empty:
            return
        table = _table(doc, name)
    for k in [k for k in table if k not in entries]:
        del table[k]
    for k, v in entries.items():
        _set(table, k, v)
    if not entries and not keep_empty:
        del doc[name]


def _set_named(doc, name: str, entries: dict[str, dict[str, object]]) -> None:
    """[name."<entry>"] sub-tables: entries are kept in place and edited key by
    key; None values remove the key."""
    parent = doc.get(name)
    if not isinstance(parent, Table):
        if not entries:
            return
        parent = tomlkit.table(is_super_table=True)
        doc[name] = parent
    for k in [k for k in parent if k not in entries]:
        del parent[k]
    for entry, values in entries.items():
        t = parent.get(entry)
        if not isinstance(t, Table):
            t = tomlkit.table()
            parent[entry] = t
        for k, v in values.items():
            _set(t, k, v)
    if not entries:
        del doc[name]
