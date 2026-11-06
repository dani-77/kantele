"""spitfire backend: settings on top of ~/.config/spitfire/config.lua.

Same approach as wasp (see luautil): Kantele owns a generated kantele.lua
that config.lua loads from its last line, and never rewrites config.lua
itself. kantele.lua holds:

- settings: fields set on spitfire's tables (spitfire.border.width, ...)
  after config.lua set its own;
- keys: bindings. spitfire's binds are Lua closures and the first match
  wins, so each Kantele binding first calls spitfire.unbind(mods, key)
  (spitfire 0.5.5+) to drop config.lua's binding for that key, then binds
  its own. The "none" action only unbinds, so the key reaches the window.

To show the current values Kantele runs config.lua with the system Lua
and a stand-in `spitfire` table that records settings and binds without
doing anything. config.lua's binds are closures, so Kantele can't name
their action; it shows the line of config.lua that defines each one.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import running_pids
from .luautil import (
    HEADER, LuaError, Spec, add_loader, coerce, get_path, lua_literal,
    overrides_tree, run, write_checked,
)

NAME = "spitfire"
EXAMPLE = Path("/usr/share/spitfire/config.lua")
OVERRIDES_NAME = "kantele.lua"

LOADER_MARK = "-- Kantele: load kantele.lua last."
LOADER = (
    LOADER_MARK + " Keep this the last line; remove it to stop using Kantele.\n"
    'do local f = (os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config"))'
    ' .. "/spitfire/kantele.lua"; local h = io.open(f);'
    " if h then h:close(); dofile(f) end end\n"
)

MOD_NAMES = ("Mod4", "Ctrl", "Mod1", "Shift")
_MOD_ALIASES = {"mod4": "Mod4", "super": "Mod4", "logo": "Mod4", "cmd": "Mod4",
                "ctrl": "Ctrl", "control": "Ctrl", "mod1": "Mod1", "alt": "Mod1",
                "shift": "Shift"}
LAYOUTS = ("tile", "floating", "fibonacci", "monocle")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
KEYSYM_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Defaults mirror spitfire's own (spitfire-config, 0.5.x) for fields
# config.lua leaves out.
SPECS: dict[str, list[Spec]] = {
    "Windows": [
        Spec(("border", "width"), "Border width", "int", 2, 0, 50),
        Spec(("border", "radius"), "Corner radius", "int", 0, 0, 100),
        Spec(("border", "active"), "Focused border", "color", "#7aa2f7"),
        Spec(("border", "inactive"), "Unfocused border", "color", "#414868"),
        Spec(("gaps", "inner"), "Gap between windows", "int", 6, 0, 200),
        Spec(("gaps", "outer"), "Gap at screen edges", "int", 10, 0, 200),
        Spec(("snap",), "Snap dragged windows to edges (px, 0 = off)", "int", 32, 0, 500),
        Spec(("focus_follows_mouse",), "Focus follows the mouse", "bool", False),
        Spec(("output", "scale"), "Output scale", "float", 1.0, 1.0, 4.0),
    ],
    "Bar": [
        Spec(("bar", "enable"), "Show the built-in bar", "bool", False),
        Spec(("bar", "height"), "Height", "int", 24, 10, 100),
        Spec(("bar", "bg"), "Background", "color", "#1e1e2e"),
        Spec(("bar", "fg"), "Text", "color", "#6c7086"),
        Spec(("bar", "fg_active"), "Active text", "color", "#cdd6f4"),
    ],
    "Keyboard": [
        Spec(("keyboard", "layout"), "Layout (e.g. us, pt)", "str", ""),
        Spec(("keyboard", "variant"), "Variant", "str", ""),
        Spec(("keyboard", "model"), "Model", "str", ""),
        Spec(("keyboard", "options"), "Options (e.g. ctrl:nocaps)", "str", ""),
        Spec(("keyboard", "repeat_rate"), "Repeat rate (per second)", "int", 25, 1, 200),
        Spec(("keyboard", "repeat_delay"), "Repeat delay (ms)", "int", 600, 50, 3000),
    ],
    "Effects": [
        Spec(("anim", "enabled"), "Animations", "bool", True),
        Spec(("anim", "duration"), "Animation duration (ms)", "int", 150, 0, 5000),
        Spec(("blur", "radius"), "Blur radius (windows with a blur rule)", "int", 20, 0, 200),
    ],
}
ALL_SPECS = [s for group in SPECS.values() for s in group]

# action -> (description, argument kind: None | "cmd" | "int" | "float" | "layout")
ACTIONS: dict[str, tuple[str, str | None]] = {
    "spawn": ("Run a command", "cmd"),
    "layout.set": ("Set layout", "layout"),
    "layout.cycle": ("Next layout", None),
    "mfact.inc": ("Resize main area", "float"),
    "nmaster.inc": ("Change number of main windows", "int"),
    "window.close": ("Close window", None),
    "window.focus_next": ("Focus next window", None),
    "window.focus_prev": ("Focus previous window", None),
    "window.swap_next": ("Move window down the stack", None),
    "window.swap_prev": ("Move window up the stack", None),
    "window.toggle_scratchpad": ("Toggle scratchpad", None),
    "workspace.focus": ("Go to workspace", "int"),
    "workspace.move_window": ("Move window to workspace", "int"),
    "workspace.next": ("Next workspace", None),
    "workspace.prev": ("Previous workspace", None),
    "reload": ("Reload config", None),
    "quit": ("Quit spitfire", None),
    "none": ("Disabled (key goes to the window)", None),
}
HINTS = {"cmd": "command, e.g. foot -e fish", "int": "whole number, e.g. 1 or -1",
         "float": "e.g. 0.05 or -0.05", "layout": " / ".join(LAYOUTS)}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "spitfire"


# ── keybindings ──────────────────────────────────────────────────────────
@dataclass
class Bind:
    combo: str     # "Mod4+Shift+Return"
    action: str
    arg: str = ""  # text form; for config.lua's binds, where they're defined

    @property
    def mods(self) -> str:
        return "+".join(self.combo.split("+")[:-1])

    @property
    def key(self) -> str:
        return self.combo.split("+")[-1]


def normalize_combo(combo: str) -> str:
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        return ""
    mods = {_MOD_ALIASES.get(m.lower(), m) for m in parts[:-1]}
    ordered = [m for m in MOD_NAMES if m in mods] + sorted(mods - set(MOD_NAMES))
    return "+".join([*ordered, parts[-1]])


def combo_of(mods: str, key: str) -> str:
    return normalize_combo(f"{mods}+{key}" if mods else key)


def combo_from_penrose(k: str, modkey: str = "") -> str:
    """KeyCaptureDialog's "M-S-x" -> "Mod4+Shift+x"."""
    *mods, key = k.split("-")
    names = {"M": "Mod4", "C": "Ctrl", "A": "Mod1", "S": "Shift"}
    return combo_of("+".join(names[m] for m in mods), key)


def entry_from_bind(b: Bind) -> dict:
    """Bind -> a kantele.lua keys entry. Assumes validate() passed."""
    combo = normalize_combo(b.combo)
    b = Bind(combo, b.action, b.arg)
    e: dict = {"mods": b.mods, "key": b.key, "action": b.action}
    kind = ACTIONS[b.action][1]
    a = b.arg.strip()
    if kind in ("cmd", "layout"):
        e["arg"] = a
    elif kind == "int":
        e["arg"] = int(a)
    elif kind == "float":
        e["arg"] = float(a)
    return e


def bind_from_entry(e: dict) -> Bind:
    arg = e.get("arg")
    return Bind(combo_of(str(e.get("mods", "")), str(e.get("key", ""))),
                str(e.get("action", "")), "" if arg is None else str(arg))


def _arg_error(b: Bind) -> str | None:
    kind = ACTIONS[b.action][1]
    a = b.arg.strip()
    if kind == "cmd" and not a:
        return "spawn needs a command"
    if kind == "int" and not re.fullmatch(r"-?\d+", a):
        return f"{b.action} needs a whole number"
    if kind == "float":
        try:
            float(a)
        except ValueError:
            return f"{b.action} needs a number such as 0.05 or -0.05"
    if kind == "layout" and a not in LAYOUTS:
        return "layout must be " + ", ".join(LAYOUTS)
    if kind is None and a:
        return f"{b.action} takes no argument"
    if b.action in ("workspace.focus", "workspace.move_window") and a.strip() == "0":
        return "workspaces start at 1"
    return None


# ── settings model ───────────────────────────────────────────────────────
@dataclass
class Settings:
    values: dict[tuple[str, ...], object] = field(default_factory=dict)
    base: dict[tuple[str, ...], object] = field(default_factory=dict)
    binds: list[Bind] = field(default_factory=list)
    base_binds: list[Bind] = field(default_factory=list)
    shell_autostart: bool = False  # kantele.lua adds `kantele-shell start`

    def overrides(self) -> dict[tuple[str, ...], object]:
        return {p: v for p, v in self.values.items() if v != self.base.get(p)}


# ── Lua ──────────────────────────────────────────────────────────────────
# arg[1] = config.lua or kantele.lua, arg[2] = "skip" (ignore kantele.lua),
# arg[3] = "return" (dump the chunk's return value), arg[4] = the kantele.lua
# that the loader line should find (the real one lives in $XDG_CONFIG_HOME).
_DUMP_LUA = r'''
local file, skip, what, mine = arg[1], arg[2] == "skip", arg[3], arg[4]
-- The loader line finds kantele.lua through $XDG_CONFIG_HOME; point that at
-- the directory above the kantele.lua being checked.
local getenv = os.getenv
os.getenv = function(name)
  if name == "XDG_CONFIG_HOME" then return (mine:match("^(.*)/[^/]+/[^/]+$")) end
  return getenv(name)
end
local real = dofile
dofile = function(f, ...)
  if f and f:match("/kantele%.lua$") then
    if skip then return end
    return real(mine, ...)
  end
  return real(f, ...)
end
-- A stand-in for spitfire's API: any function call is a no-op, settings are
-- plain fields, and binds are recorded with where they were defined.
local function stub()
  return setmetatable({}, {
    __call = function() end,
    __index = function(t, k) local v = stub(); rawset(t, k, v); return v end,
  })
end
spitfire = stub()
local binds = {}
local function norm_key(k)
  k = tostring(k)
  return (#k == 1) and k:lower() or k
end
local function norm_mods(m)
  local set = {}
  for part in tostring(m):gmatch("[^+]+") do
    local p = part:lower():gsub("%s", "")
    if p == "super" or p == "logo" or p == "cmd" then p = "mod4" end
    if p == "alt" then p = "mod1" end
    if p == "control" then p = "ctrl" end
    set[p] = true
  end
  local out = {}
  for _, p in ipairs({ "mod4", "ctrl", "mod1", "shift" }) do
    if set[p] then out[#out + 1] = p end
  end
  return table.concat(out, "+")
end
rawset(spitfire, "bind", function(mods, key, fn)
  local info = type(fn) == "function" and debug.getinfo(fn, "S") or {}
  binds[#binds + 1] = { mods = mods, key = key, line = info.linedefined,
                        src = info.short_src }
end)
rawset(spitfire, "unbind", function(mods, key)
  local m, k, n = norm_mods(mods), norm_key(key), 0
  for i = #binds, 1, -1 do
    if norm_mods(binds[i].mods) == m and norm_key(binds[i].key) == k then
      table.remove(binds, i); n = n + 1
    end
  end
  return n
end)
local ret = real(file)
if what == "return" then
  io.write(enc(ret))
else
  local s = {}
  for _, k in ipairs({ "border", "gaps", "anim", "blur", "keyboard", "output",
                       "bar", "focus_follows_mouse", "snap" }) do
    s[k] = rawget(spitfire, k)
  end
  io.write(enc({ settings = s, binds = binds }))
end
'''


def _run_lua(file: Path, skip: bool, what: str = "", mine: Path | None = None):
    return run(_DUMP_LUA, file, "skip" if skip else "", what,
               str(mine or file.with_name(OVERRIDES_NAME)))


_APPLY = """
for k, v in pairs(settings) do
  if type(v) == "table" then
    if type(spitfire[k]) ~= "table" then spitfire[k] = {} end
    for f, x in pairs(v) do spitfire[k][f] = x end
  else
    spitfire[k] = v
  end
end

local actions = {
  spawn = function(a) spitfire.spawn(a) end,
  ["layout.set"] = function(a) spitfire.layout.set(a) end,
  ["layout.cycle"] = function() spitfire.layout.cycle() end,
  ["mfact.inc"] = function(a) spitfire.mfact.inc(a) end,
  ["nmaster.inc"] = function(a) spitfire.nmaster.inc(a) end,
  ["window.close"] = function() spitfire.window.close() end,
  ["window.focus_next"] = function() spitfire.window.focus_next() end,
  ["window.focus_prev"] = function() spitfire.window.focus_prev() end,
  ["window.swap_next"] = function() spitfire.window.swap_next() end,
  ["window.swap_prev"] = function() spitfire.window.swap_prev() end,
  ["window.toggle_scratchpad"] = function() spitfire.window.toggle_scratchpad() end,
  ["workspace.focus"] = function(a) spitfire.workspace.focus(a) end,
  ["workspace.move_window"] = function(a) spitfire.workspace.move_window(a) end,
  ["workspace.next"] = function() spitfire.workspace.next() end,
  ["workspace.prev"] = function() spitfire.workspace.prev() end,
  reload = function() spitfire.reload() end,
  quit = function() spitfire.quit() end,
}

-- The first matching bind wins: drop config.lua's binding for each key
-- first (spitfire.unbind, spitfire 0.5.5+), then add ours. "none" only
-- drops it.
for _, k in ipairs(keys) do
  if spitfire.unbind then spitfire.unbind(k.mods, k.key) end
  local f = actions[k.action]
  if f then
    local a = k.arg
    spitfire.bind(k.mods, k.key, function() f(a) end)
  end
end

-- spitfire.autostart adds to the list, so config.lua's own entries stay.
if shell_autostart then
  spitfire.autostart({ "kantele-shell start" })
end

return { settings = settings, keys = keys, shell_autostart = shell_autostart }
"""


def render_overrides(s: Settings) -> str:
    tree = overrides_tree(ALL_SPECS, s.values, s.base)
    keys = [entry_from_bind(b) for b in s.binds]
    return (HEADER + "local settings = " + lua_literal(tree) + "\n\n"
            + "local keys = " + lua_literal(keys) + "\n\n"
            + "local shell_autostart = " + lua_literal(s.shell_autostart) + "\n" + _APPLY)


# ── config ───────────────────────────────────────────────────────────────
class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "config.lua"
        self.overrides_path = self.path.with_name(OVERRIDES_NAME)
        self.existed = self.path.exists()

    def _source(self) -> Path | None:
        if self.existed:
            return self.path
        return EXAMPLE if EXAMPLE.exists() else None

    def read(self) -> Settings:
        s = Settings()
        src = self._source()
        dump = _run_lua(src, skip=True) if src else {}
        settings = (dump or {}).get("settings") or {}
        for spec in ALL_SPECS:
            s.base[spec.path] = coerce(spec, get_path(settings, spec.path))
        lines = src.read_text().splitlines() if src else []
        for b in (dump or {}).get("binds") or []:
            line = b.get("line")
            where = ""
            if isinstance(line, int) and 0 < line <= len(lines):
                where = f"line {line}: {lines[line - 1].strip()}"
            s.base_binds.append(Bind(combo_of(str(b.get("mods", "")), str(b.get("key", ""))),
                                     "lua", where))
        s.values = dict(s.base)
        if self.overrides_path.exists():
            mine = _run_lua(self.overrides_path, skip=False, what="return") or {}
            for spec in ALL_SPECS:
                v = get_path(mine.get("settings") or {}, spec.path)
                if v is not None:
                    s.values[spec.path] = coerce(spec, v)
            s.binds = [bind_from_entry(e) for e in mine.get("keys") or []
                       if isinstance(e, dict)]
            s.shell_autostart = bool(mine.get("shell_autostart"))
        return s

    def save(self, s: Settings) -> Path | None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.existed:
            if not EXAMPLE.exists():
                raise LuaError(f"No {self.path} and no {EXAMPLE} to start from.")
            shutil.copy(EXAMPLE, self.path)
            self.existed = True
        backup = add_loader(self.path, LOADER_MARK, LOADER)
        write_checked(self.overrides_path, render_overrides(s),
                      lambda: _run_lua(self.path, skip=False))
        return backup


def validate(s: Settings) -> list[str]:
    errs: list[str] = []
    for spec in ALL_SPECS:
        v = s.values.get(spec.path)
        if spec.kind == "color" and not COLOR_RE.match(str(v)):
            errs.append(f"{spec.label}: '{v}' is not a #RRGGBB color.")
    seen: set[str] = set()
    for b in s.binds:
        combo = normalize_combo(b.combo)
        if not combo or not KEYSYM_RE.match(b.key):
            errs.append(f"Key '{b.combo}' is not like Mod4+Shift+Return.")
            continue
        bad = [m for m in combo.split("+")[:-1] if m not in MOD_NAMES]
        if bad:
            errs.append(f"Key '{b.combo}': unknown modifier {', '.join(bad)} "
                        "(use Mod4, Ctrl, Mod1, Shift).")
        if combo in seen:
            errs.append(f"Key '{b.combo}' is bound more than once.")
        seen.add(combo)
        if b.action not in ACTIONS:
            errs.append(f"Key '{b.combo}': unknown action '{b.action}'.")
            continue
        e = _arg_error(b)
        if e:
            errs.append(f"Key '{b.combo}': {e}.")
    return errs


def reload_running() -> str:
    if not running_pids(NAME):
        return ("Saved. spitfire isn't running; it will use the new settings next "
                "time it starts.")
    try:
        p = subprocess.run(["spitfirectl", "reload"], capture_output=True, text=True,
                           timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Saved, but spitfirectl reload failed ({e}): press Mod4+Shift+R."
    if p.returncode != 0:
        return ("Saved, but spitfirectl reload failed: "
                f"{(p.stderr or p.stdout).strip()}. Press Mod4+Shift+R.")
    return "Saved and applied."
