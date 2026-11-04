"""pwm backend: reads, validates and writes ~/.config/pwm/config.toml.

pwm's config is plain declarative TOML that pwm overlays onto its built-in
defaults, so every setting here is optional: an empty value means "remove
the key and let pwm use its default". The file is edited with tomlkit, which
keeps the user's comments and layout intact.

The defaults below mirror pwm's src/user_config.rs and src/keybindings.rs
(pwm 0.6.x); keep them in sync when pwm changes.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from tomlkit.items import AoT, Table

from . import send_reload

NAME = "pwm"
EXAMPLE = Path("/usr/share/pwm/config.toml.example")

DEFAULT_FONT = "JetBrainsMono Nerd Font"
DEFAULT_THEME = "d77"

# name -> (black, white, grey, accent)
BUILTIN_THEMES: dict[str, tuple[str, str, str, str]] = {
    "d77": ("#282828", "#ebdbb2", "#3c3836", "#aa96da"),
    "gruvbox_dark": ("#282828", "#ebdbb2", "#3c3836", "#fe8019"),
    "arc_dark": ("#2f343f", "#d3dae3", "#353945", "#5294e2"),
    "dracula": ("#282a36", "#f8f8f2", "#44475a", "#bd93f9"),
    "tokyo_night": ("#1a1b26", "#c0caf5", "#414868", "#bb9af7"),
}
THEME_FIELDS = ("black", "white", "grey", "accent")

DEFAULT_APPS = {
    "terminal": "st",
    "launcher": "dmenu_run",
    "locker": "slock",
    "startup_script": "/etc/xdg/pwm/startup.sh",
}

DEFAULT_WINDOW_RULES = [
    ("gimp", "3"), ("deadbeef", "5"), ("mpv", "5"), ("ncspot", "5"),
    ("spotify", "5"), ("thunderbird", "9"), ("chromium", "9"),
    ("firefox", "9"), ("qutebrowser", "9"),
]
WORKSPACES = [str(i) for i in range(1, 10)]
DEFAULT_FLOAT_RATIO = 0.6

BAR_WIDGETS = [
    "workspaces", "layout", "window_name",
    "cpu", "ram", "volume", "wifi", "battery", "clock",
]

# action -> (description, argument: None | "int" | "command")
ACTIONS: dict[str, tuple[str, str | None]] = {
    "focus_down": ("Focus next window", None),
    "focus_up": ("Focus previous window", None),
    "swap_down": ("Move window down the stack", None),
    "swap_up": ("Move window up the stack", None),
    "kill_focused": ("Close focused window", None),
    "toggle_fullscreen": ("Toggle fullscreen", None),
    "toggle_tag": ("Go to previous workspace", None),
    "next_screen": ("Focus next screen", None),
    "previous_screen": ("Focus previous screen", None),
    "next_layout": ("Next layout", None),
    "previous_layout": ("Previous layout", None),
    "expand_main": ("Grow main area", None),
    "shrink_main": ("Shrink main area", None),
    "inc_main": ("Change number of main windows", "int"),
    "spawn_terminal": ("Open terminal", None),
    "spawn_launcher": ("Open launcher", None),
    "spawn_locker": ("Lock screen", None),
    "spawn": ("Run a command", "command"),
    "toggle_scratchpad": ("Toggle scratchpad terminal", None),
    "logout_menu": ("Logout menu", None),
    "log_state": ("Log window manager state", None),
    "exit": ("Quit pwm", None),
    "restart": ("Restart pwm (re-reads config.toml)", None),
}

# The keymap pwm ships with; [[bind]] entries override it key by key.
DEFAULT_BINDS: list[tuple[str, str, str | None]] = [
    ("M-j", "focus_down", None),
    ("M-k", "focus_up", None),
    ("M-S-j", "swap_down", None),
    ("M-S-k", "swap_up", None),
    ("M-q", "kill_focused", None),
    ("M-S-f", "toggle_fullscreen", None),
    ("M-Tab", "toggle_tag", None),
    ("M-period", "next_screen", None),
    ("M-comma", "previous_screen", None),
    ("M-m", "next_layout", None),
    ("M-S-m", "previous_layout", None),
    ("M-Up", "inc_main", "1"),
    ("M-Down", "inc_main", "-1"),
    ("M-Right", "expand_main", None),
    ("M-Left", "shrink_main", None),
    ("M-Return", "spawn_terminal", None),
    ("M-d", "spawn_launcher", None),
    ("M-t", "spawn_locker", None),
    ("M-x", "logout_menu", None),
    ("M-S-s", "log_state", None),
    ("M-S-q", "exit", None),
    ("M-S-r", "restart", None),
    ("M-s", "toggle_scratchpad", None),
    ("XF86AudioRaiseVolume", "spawn", "pactl set-sink-volume @DEFAULT_SINK@ +5%"),
    ("XF86AudioLowerVolume", "spawn", "pactl set-sink-volume @DEFAULT_SINK@ -5%"),
    ("XF86AudioMute", "spawn", "pactl set-sink-mute @DEFAULT_SINK@ toggle"),
]

# penrose key strings: optional modifiers (M=super, S=shift, C=ctrl, A=alt)
# joined by '-', then one keysym name.
KEY_RE = re.compile(r"^(?:[MSCA]-)*[A-Za-z0-9_]+$")
COLOR_RE = re.compile(r"^(?:#|0x)?(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "pwm" / "config.toml"


@dataclass
class Bind:
    key: str
    action: str
    arg: str | None = None


@dataclass
class FloatRule:
    cls: str
    width: float | None = None
    height: float | None = None


@dataclass
class Settings:
    """Everything the GUI edits; empty/None means "pwm default"."""

    theme: str | None = None
    palettes: dict[str, dict[str, str]] = field(default_factory=dict)
    apps: dict[str, str] = field(default_factory=dict)
    window_rules: list[tuple[str, str]] = field(default_factory=list)
    float_rules: list[FloatRule] = field(default_factory=list)
    bar_widgets: list[str] | None = None
    binds: list[Bind] = field(default_factory=list)


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_path()
        self.existed = self.path.exists()
        if self.existed:
            self.doc = tomlkit.parse(self.path.read_text())
        elif EXAMPLE.exists():
            # start from the commented example, like pwm's own docs suggest
            self.doc = tomlkit.parse(EXAMPLE.read_text())
        else:
            self.doc = tomlkit.document()

    # ── reading ──────────────────────────────────────────────────────────
    def read(self) -> Settings:
        d = self.doc
        s = Settings()
        theme = d.get("theme", {})
        s.theme = theme.get("active")
        for name, val in theme.items():
            if name != "active" and isinstance(val, dict):
                s.palettes[name] = {k: str(v) for k, v in val.items()}
        s.apps = {k: str(v) for k, v in d.get("apps", {}).items() if k in DEFAULT_APPS}
        s.window_rules = [(str(r.get("class", "")), str(r.get("workspace", "")))
                          for r in d.get("window_rule", [])]
        s.float_rules = [FloatRule(str(r.get("class", "")), r.get("width_ratio"),
                                   r.get("height_ratio"))
                         for r in d.get("float_rule", [])]
        widgets = d.get("bar", {}).get("widgets")
        s.bar_widgets = [str(w) for w in widgets] if widgets is not None else None
        s.binds = [Bind(str(b.get("key", "")), str(b.get("action", "")),
                        str(b["arg"]) if "arg" in b else None)
                   for b in d.get("bind", [])]
        return s

    # ── writing ──────────────────────────────────────────────────────────
    def apply(self, s: Settings) -> None:
        """Writes `s` into the TOML document, keeping comments where the
        structure allows (scalar keys are edited in place)."""
        d = self.doc

        theme = _table(d, "theme")
        _set(theme, "active", s.theme)
        for name in [k for k, v in theme.items() if k != "active" and isinstance(v, dict)]:
            if name not in s.palettes:
                del theme[name]
        for name, pal in s.palettes.items():
            t = theme.get(name)
            if not isinstance(t, Table):
                t = tomlkit.table()
                theme[name] = t
            for k in (*THEME_FIELDS, "font"):
                _set(t, k, pal.get(k) or None)

        apps = _table(d, "apps")
        for k in DEFAULT_APPS:
            _set(apps, k, s.apps.get(k) or None)

        _set_aot(d, "window_rule", [{"class": c, "workspace": w} for c, w in s.window_rules])
        _set_aot(d, "float_rule", [
            {k: v for k, v in (("class", r.cls), ("width_ratio", r.width),
                               ("height_ratio", r.height)) if v is not None}
            for r in s.float_rules])

        bar = _table(d, "bar")
        _set(bar, "widgets", s.bar_widgets)

        _set_aot(d, "bind", [
            {k: v for k, v in (("key", b.key), ("action", b.action), ("arg", b.arg))
             if v is not None}
            for b in s.binds])

    def save(self) -> Path | None:
        """Writes the file atomically. The first time kantele touches an
        existing config it keeps a copy next to it; returns that path."""
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


def validate(s: Settings) -> list[str]:
    """Problems pwm would reject or silently ignore, as readable messages."""
    errs: list[str] = []
    known_themes = set(BUILTIN_THEMES) | set(s.palettes)
    if s.theme and s.theme not in known_themes:
        errs.append(f"Theme '{s.theme}' is neither built in nor defined below.")
    for name, pal in s.palettes.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            errs.append(f"Theme name '{name}' may only use letters, digits, '_' and '-'.")
        for k in THEME_FIELDS:
            v = pal.get(k, "")
            if not v:
                errs.append(f"Theme '{name}' needs a {k} color.")
            elif not COLOR_RE.match(v):
                errs.append(f"Theme '{name}': {k} '{v}' is not a #RRGGBB[AA] color.")
    for c, w in s.window_rules:
        if not c:
            errs.append("A window rule has an empty class.")
        if w not in WORKSPACES:
            errs.append(f"Window rule '{c}': workspace must be 1-9.")
    for r in s.float_rules:
        if not r.cls:
            errs.append("A floating rule has an empty class.")
        for label, v in (("width", r.width), ("height", r.height)):
            if v is not None and not 0.0 < v <= 1.0:
                errs.append(f"Floating rule '{r.cls}': {label} must be between 0 and 1.")
    if s.bar_widgets is not None:
        for w in s.bar_widgets:
            if w not in BAR_WIDGETS:
                errs.append(f"Unknown bar widget '{w}'.")
    seen: set[str] = set()
    for b in s.binds:
        if not KEY_RE.match(b.key):
            errs.append(f"Key '{b.key}' is not in penrose format (e.g. M-S-Return).")
        if b.key in seen:
            errs.append(f"Key '{b.key}' is bound more than once.")
        seen.add(b.key)
        if b.action not in ACTIONS:
            errs.append(f"Key '{b.key}': unknown action '{b.action}'.")
            continue
        kind = ACTIONS[b.action][1]
        if kind == "int":
            if b.arg is None or not re.fullmatch(r"-?\d+", b.arg):
                errs.append(f"Key '{b.key}': {b.action} needs a whole number (e.g. 1 or -1).")
        elif kind == "command":
            if not b.arg:
                errs.append(f"Key '{b.key}': spawn needs a command.")
    if sum(b.action == "toggle_scratchpad" for b in s.binds) > 1:
        errs.append("toggle_scratchpad can only be bound to one key.")
    return errs


# ── applying to the running pwm ──────────────────────────────────────────
def reload_running() -> str:
    """Asks the running pwm to re-read its config. Returns a status message."""
    r = send_reload(NAME)
    if r == "absent":
        return "Saved. pwm isn't running; it will use the new settings next time it starts."
    if r == "unsupported":
        return ("Saved. This pwm can't reload on request (needs pwm 0.6.5 or newer): "
                "press Super+Shift+R to apply.")
    return "Saved and applied."


# ── tomlkit helpers ──────────────────────────────────────────────────────
def _table(doc, name: str) -> Table:
    t = doc.get(name)
    if not isinstance(t, Table):
        t = tomlkit.table()
        doc[name] = t
    return t


def _plain(v):
    return v.unwrap() if hasattr(v, "unwrap") else v


def _set(table, key: str, value) -> None:
    """Sets/removes `key`, touching the document only when the value really
    changes, so an unchanged setting keeps its original formatting."""
    if value is None or value == "":
        if key in table:
            del table[key]
    elif key not in table or _plain(table[key]) != value:
        table[key] = value


def _set_aot(doc, name: str, rows: list[dict]) -> None:
    """Edits an array of tables ([[name]]) in place: existing entries are
    updated key by key and keep their position and surrounding comments;
    only surplus entries are dropped and new ones appended."""
    aot = doc.get(name)
    if not isinstance(aot, AoT):
        if not rows:
            return
        aot = AoT([])
        doc[name] = aot
    for i, row in enumerate(rows):
        if i < len(aot):
            t = aot[i]
            for k in [k for k in t if k not in row]:
                del t[k]
            for k, v in row.items():
                _set(t, k, v)
        else:
            t = tomlkit.table()
            for k, v in row.items():
                t[k] = v
            aot.append(t)
    while len(aot) > len(rows):
        del aot[len(aot) - 1]
    if not rows:
        del doc[name]
