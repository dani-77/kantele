"""wasp backend: settings on top of ~/.config/wasp/config.lua.

wasp's config is Lua code, not data, so Kantele never rewrites it. Instead it
owns a generated file next to it, kantele.lua, which config.lua loads with
one line at its very end (Kantele appends that line the first time it saves).
kantele.lua holds only what you changed in Kantele:

- settings: values merged over whatever config.lua set (tables are merged
  key by key, arrays such as wasp.terminal are replaced);
- keys: bindings put at the *front* of wasp.keys. wasp uses the first
  binding that matches, so these win over config.lua's. The "none" action
  (wasp 0.10.1+) switches a config.lua binding off.

To show the current values Kantele runs config.lua with the system Lua
(lua5.4) with kantele.lua skipped, and dumps the resulting `wasp` table.
Deleting kantele.lua drops every Kantele setting; config.lua stays yours.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import send_reload

NAME = "wasp"
LUA = "lua5.4"
EXAMPLE = Path("/usr/share/wasp/config.lua")
OVERRIDES_NAME = "kantele.lua"

LOADER_MARK = "-- Kantele: load kantele.lua last."
LOADER = (
    LOADER_MARK + " Keep this the last line; remove it to stop using Kantele.\n"
    'do local d = debug.getinfo(1, "S").source:match("^@(.*/)") or "./";'
    ' local f = d .. "kantele.lua"; local h = io.open(f);'
    " if h then h:close(); dofile(f) end end\n"
)

MODKEYS = ("alt", "ctrl", "super", "shift")
MOD_NAMES = ("mod", "super", "ctrl", "alt", "shift")
LAYOUTS = ("tile", "floating", "monocle", "dwindle")
ANIM_TYPES = ("zoom", "fade", "none")
DIRECTIONS = ("left", "right", "up", "down")

COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
KEYSYM_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class Spec:
    """One scalar setting: where it lives in the `wasp` table and how to edit it."""

    path: tuple[str, ...]
    label: str
    kind: str  # "int" | "float" | "bool" | "color" | "str" | "argv" | "choice"
    default: object
    lo: float = 0
    hi: float = 0
    choices: tuple[str, ...] = ()


# Defaults mirror wasp's examples/config.lua (wasp 0.10.x), used when the
# user's config.lua leaves a field out.
SPECS: dict[str, list[Spec]] = {
    "Windows": [
        Spec(("border", "width"), "Border width", "int", 2, 0, 50),
        Spec(("border", "radius"), "Corner radius", "int", 0, 0, 100),
        Spec(("border", "focus"), "Focused border", "color", "#7aa2f7"),
        Spec(("border", "normal"), "Unfocused border", "color", "#414868"),
        Spec(("gaps", "inner"), "Gap between windows", "int", 0, 0, 200),
        Spec(("gaps", "outer"), "Gap at screen edges", "int", 0, 0, 200),
        Spec(("gaps", "smart"), "No outer gap with one window", "bool", False),
        Spec(("snap",), "Snap floating windows to edges (px, 0 = off)", "int", 32, 0, 500),
        Spec(("background",), "Background color", "color", "#11111bff"),
    ],
    "Bar": [
        Spec(("bar", "enable"), "Show the built-in bar", "bool", True),
        Spec(("bar", "top"), "Bar at the top", "bool", True),
        Spec(("bar", "layout"), "Bar layout (t=tags l=layout n=title s=status, | splits)",
             "str", "tln|s"),
    ],
    "Keyboard": [
        Spec(("modkey",), "Mod key", "choice", "alt", choices=MODKEYS),
        Spec(("keyboard", "layout"), "Layout (e.g. us, pt)", "str", "us"),
        Spec(("keyboard", "variant"), "Variant", "str", ""),
        Spec(("keyboard", "model"), "Model", "str", ""),
        Spec(("keyboard", "options"), "Options (e.g. ctrl:nocaps)", "str", ""),
        Spec(("keyboard", "repeat_rate"), "Repeat rate (per second)", "int", 25, 1, 200),
        Spec(("keyboard", "repeat_delay"), "Repeat delay (ms)", "int", 600, 50, 3000),
    ],
    "Applications": [
        Spec(("terminal",), "Terminal", "argv", ["alacritty"]),
        Spec(("menu",), "Launcher", "argv", ["wmenu-run"]),
    ],
    "Effects": [
        Spec(("animations", "enable"), "Animations", "bool", False),
        Spec(("animations", "duration_open"), "Open duration (ms)", "int", 200, 0, 5000),
        Spec(("animations", "duration_close"), "Close duration (ms)", "int", 150, 0, 5000),
        Spec(("animations", "duration_move"), "Move duration (ms)", "int", 200, 0, 5000),
        Spec(("animations", "duration_tag"), "Workspace switch duration (ms)", "int", 200, 0, 5000),
        Spec(("animations", "type_open"), "Open animation", "choice", "zoom", choices=ANIM_TYPES),
        Spec(("animations", "type_close"), "Close animation", "choice", "zoom", choices=ANIM_TYPES),
        Spec(("animations", "tag_direction"), "Workspace slide direction", "choice", "right",
             choices=DIRECTIONS),
        Spec(("blur", "enable"), "Blur (new windows only)", "bool", False),
        Spec(("blur", "radius"), "Blur radius", "int", 5, 0, 100),
        Spec(("blur", "passes"), "Blur passes", "int", 3, 0, 10),
    ],
}
ALL_SPECS = [s for group in SPECS.values() for s in group]

# action -> (description, argument kind). Argument kinds and their text form:
#   None          no argument
#   "cmd"         command line, split like a shell would (cmd = {...})
#   "dir"         whole number, usually 1 or -1 (dir = n)
#   "mondir"      left/right/up/down (dir = "...")
#   "delta"       decimal number (delta = x)
#   "tag"         1-9, "all", or empty for "previous" (tag = ...)
#   "layout"      tile/floating/monocle/dwindle, or empty to cycle
#   "vt"          VT number (vt = n)
#   "moveresize"  dx=.. dy=.. dw=.. dh=.. in pixels
#   "name"        scratchpad slot name (name = "...")
ACTIONS: dict[str, tuple[str, str | None]] = {
    "spawn": ("Run a command", "cmd"),
    "spawn-terminal": ("Open terminal", None),
    "spawn-menu": ("Open launcher", None),
    "focusstack": ("Focus next/previous window", "dir"),
    "movestack": ("Move window in the stack", "dir"),
    "zoom": ("Swap with the main window", None),
    "incnmaster": ("Change number of main windows", "dir"),
    "setmfact": ("Resize main area", "delta"),
    "setscale": ("Change monitor scale", "delta"),
    "view": ("Go to workspace", "tag"),
    "viewshift": ("Next/previous workspace", "dir"),
    "toggleview": ("Also show workspace", "tag"),
    "tag": ("Move window to workspace", "tag"),
    "toggletag": ("Also put window on workspace", "tag"),
    "focusmon": ("Focus monitor", "mondir"),
    "tagmon": ("Move window to monitor", "mondir"),
    "setlayout": ("Set layout", "layout"),
    "togglefloating": ("Toggle floating", None),
    "togglefullscreen": ("Toggle fullscreen", None),
    "togglebar": ("Toggle bar", None),
    "toggle-scratchpad": ("Toggle scratchpad", "name"),
    "killclient": ("Close window", None),
    "moveresizekb": ("Nudge/resize floating window", "moveresize"),
    "chvt": ("Switch virtual terminal", "vt"),
    "reload": ("Reload config", None),
    "quit": ("Quit wasp", None),
    "none": ("Disabled (key goes to the window)", None),
}
_MOVERESIZE = ("dx", "dy", "dw", "dh")
_ARG_FIELDS = {"cmd": ("cmd",), "dir": ("dir",), "mondir": ("dir",), "delta": ("delta",),
               "tag": ("tag",), "layout": ("layout",), "vt": ("vt",),
               "moveresize": _MOVERESIZE, "name": ("name",)}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "wasp"


# ── keybindings ──────────────────────────────────────────────────────────
@dataclass
class Bind:
    combo: str    # "mod+shift+Return"
    action: str
    arg: str = ""  # text form, see ACTIONS

    @property
    def mods(self) -> list[str]:
        return self.combo.split("+")[:-1]

    @property
    def key(self) -> str:
        return self.combo.split("+")[-1]


def combo_of(mods: list[str], key: str) -> str:
    order = {m: i for i, m in enumerate(MOD_NAMES)}
    ms = sorted(set(mods), key=lambda m: order.get(m, 99))
    return "+".join([*ms, key])


def normalize_combo(combo: str) -> str:
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        return ""
    mods = ["ctrl" if m.lower() in ("control", "ctrl") else
            "super" if m.lower() in ("logo", "win", "super") else m.lower()
            for m in parts[:-1]]
    return combo_of(mods, parts[-1])


def combo_from_penrose(k: str, modkey: str) -> str:
    """KeyCaptureDialog's "M-S-x" -> wasp's "mod+shift+x". The modifier that
    is wasp.modkey becomes "mod", like config.lua's own bindings."""
    *mods, key = k.split("-")
    names = {"M": "super", "C": "ctrl", "A": "alt", "S": "shift"}
    out = ["mod" if names[m] == modkey else names[m] for m in mods]
    return combo_of(out, key)


def bind_from_entry(e: dict) -> Bind:
    action = str(e.get("action", ""))
    kind = ACTIONS.get(action, ("", None))[1]
    arg = ""
    if kind == "cmd":
        cmd = e.get("cmd") or []
        arg = shlex.join(str(c) for c in cmd) if isinstance(cmd, list) else ""
    elif kind == "moveresize":
        arg = " ".join(f"{f}={e[f]}" for f in _MOVERESIZE if f in e)
    elif kind is not None and kind in _ARG_FIELDS:
        v = e.get(_ARG_FIELDS[kind][0])
        arg = "" if v is None else str(v)
    mods = [str(m) for m in (e.get("mods") or [])]
    return Bind(combo_of(mods, str(e.get("key", ""))), action, arg)


def entry_from_bind(b: Bind) -> dict:
    """Bind -> a wasp.keys entry. Assumes validate() passed."""
    b = Bind(normalize_combo(b.combo), b.action, b.arg)
    e: dict = {"mods": b.mods, "key": b.key, "action": b.action}
    kind = ACTIONS[b.action][1]
    a = b.arg.strip()
    if kind == "cmd":
        e["cmd"] = shlex.split(a)
    elif kind in ("dir", "vt"):
        if a:
            e[_ARG_FIELDS[kind][0]] = int(a)
    elif kind == "delta":
        e["delta"] = float(a)
    elif kind == "tag":
        if a:
            e["tag"] = "all" if a == "all" else int(a)
    elif kind in ("mondir", "layout", "name"):
        if a:
            e[_ARG_FIELDS[kind][0]] = a
    elif kind == "moveresize":
        for part in a.split():
            k, v = part.split("=", 1)
            e[k] = int(v)
    return e


def _arg_error(b: Bind) -> str | None:
    kind = ACTIONS[b.action][1]
    a = b.arg.strip()
    if kind == "cmd":
        try:
            if not shlex.split(a):
                return "spawn needs a command"
        except ValueError as ex:
            return f"bad command ({ex})"
    elif kind in ("dir", "vt"):
        if a and not re.fullmatch(r"-?\d+", a):
            return f"{b.action} needs a whole number"
    elif kind == "delta":
        try:
            float(a)
        except ValueError:
            return f"{b.action} needs a number such as 0.05 or -0.05"
    elif kind == "tag":
        if a and a != "all" and not re.fullmatch(r"[1-9]", a):
            return "workspace must be 1-9, 'all' or empty"
    elif kind == "mondir":
        if a not in DIRECTIONS:
            return "direction must be left, right, up or down"
    elif kind == "layout":
        if a and a not in LAYOUTS:
            return "layout must be " + ", ".join(LAYOUTS) + " or empty (cycle)"
    elif kind == "name":
        if not a:
            return "toggle-scratchpad needs a slot name"
    elif kind == "moveresize":
        for part in a.split():
            k, _, v = part.partition("=")
            if k not in _MOVERESIZE or not re.fullmatch(r"-?\d+", v):
                return "use dx=.. dy=.. dw=.. dh=.. with whole numbers"
    elif a:
        return f"{b.action} takes no argument"
    return None


# ── settings model ───────────────────────────────────────────────────────
@dataclass
class Settings:
    """values: effective value of every Spec (path -> value). base: what
    config.lua alone gives. binds: Kantele's own bindings, front first.
    base_binds: config.lua's bindings, in wasp's lookup order."""

    values: dict[tuple[str, ...], object] = field(default_factory=dict)
    base: dict[tuple[str, ...], object] = field(default_factory=dict)
    binds: list[Bind] = field(default_factory=list)
    base_binds: list[Bind] = field(default_factory=list)

    def overrides(self) -> dict[tuple[str, ...], object]:
        return {p: v for p, v in self.values.items() if v != self.base.get(p)}


def _get(t: dict, path: tuple[str, ...]):
    for k in path:
        if not isinstance(t, dict) or k not in t:
            return None
        t = t[k]
    return t


def _coerce(spec: Spec, v):
    """A value read from Lua, made to fit the spec (None -> default)."""
    if v is None:
        return spec.default
    try:
        if spec.kind == "int":
            return int(v)
        if spec.kind == "float":
            return float(v)
        if spec.kind == "bool":
            return bool(v)
        if spec.kind == "argv":
            return [str(x) for x in v] if isinstance(v, list) else spec.default
        return str(v)
    except (TypeError, ValueError):
        return spec.default


# ── Lua helpers ──────────────────────────────────────────────────────────
# Runs config.lua (or kantele.lua) and prints a JSON dump. arg[1] = file to
# run, arg[2] = "skip" to make the loader line ignore kantele.lua, arg[3] =
# "return" to dump the chunk's return value instead of the `wasp` global.
_DUMP_LUA = r'''
local file, skip, what = arg[1], arg[2] == "skip", arg[3]
if skip then
  local real = dofile
  dofile = function(f, ...)
    if f and f:match("/kantele%.lua$") then return end
    return real(f, ...)
  end
end
wasp = { keys = {} }
local function enc(v, seen)
  local t = type(v)
  if t == "nil" then return "null"
  elseif t == "boolean" then return tostring(v)
  elseif t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "null" end
    if math.type(v) == "integer" then return tostring(v) end
    return string.format("%.14g", v)
  elseif t == "string" then
    return '"' .. v:gsub('[%c"\\]', function(c)
      return string.format("\\u%04x", c:byte())
    end) .. '"'
  elseif t == "table" then
    if seen[v] then return "null" end
    seen[v] = true
    local n = #v
    local out = {}
    local is_array = n > 0
    for k in pairs(v) do
      if math.type(k) ~= "integer" or k < 1 or k > n then is_array = false break end
    end
    if is_array then
      for i = 1, n do out[#out + 1] = enc(v[i], seen) end
      seen[v] = nil
      return "[" .. table.concat(out, ",") .. "]"
    end
    for k, x in pairs(v) do
      if type(k) == "string" and type(x) ~= "function" and type(x) ~= "userdata" then
        out[#out + 1] = enc(k, seen) .. ":" .. enc(x, seen)
      end
    end
    seen[v] = nil
    return "{" .. table.concat(out, ",") .. "}"
  end
  return "null"
end
local ret = dofile(file)
io.write(enc(what == "return" and ret or wasp, {}))
'''


class LuaError(RuntimeError):
    pass


def _run_lua(file: Path, skip: bool, what: str = "wasp"):
    if not shutil.which(LUA):
        raise LuaError(f"{LUA} not found; Kantele needs it to read wasp's config.")
    p = subprocess.run([LUA, "-", str(file), "skip" if skip else "", what],
                       input=_DUMP_LUA, capture_output=True, text=True, timeout=10,
                       cwd=file.parent)
    if p.returncode != 0:
        raise LuaError(p.stderr.strip() or f"{LUA} exited with {p.returncode}")
    return json.loads(p.stdout or "null")


def lua_literal(v, indent: str = "") -> str:
    """Python value -> Lua source. Dicts keep their order, so the output is
    stable and a no-op save rewrites kantele.lua byte for byte."""
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        out = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        out = re.sub(r"[\x00-\x1f\x7f]", lambda m: "\\%03d" % ord(m.group()), out)
        return f'"{out}"'
    if isinstance(v, list):
        if all(not isinstance(x, (dict, list)) for x in v):
            return "{ " + ", ".join(lua_literal(x) for x in v) + " }" if v else "{}"
        inner = indent + "  "
        return "{\n" + "".join(f"{inner}{lua_literal(x, inner)},\n" for x in v) + indent + "}"
    if isinstance(v, dict):
        if not v:
            return "{}"
        inner = indent + "  "
        items = []
        for k, x in v.items():
            key = k if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) else f"[{lua_literal(k)}]"
            items.append(f"{key} = {lua_literal(x, inner)}")
        one = "{ " + ", ".join(items) + " }"
        if len(one) <= 80 and "\n" not in one:
            return one
        return "{\n" + "".join(f"{inner}{i},\n" for i in items) + indent + "}"
    raise TypeError(f"can't write {type(v).__name__} to Lua")


_HEADER = """\
-- Generated by Kantele (https://github.com/dani-77/kantele). Don't edit:
-- Kantele rewrites this file on every save. Delete it to drop every
-- Kantele setting; config.lua loads it from its last line.

"""

_APPLY = """
local function merge(dst, src)
  for k, v in pairs(src) do
    if type(v) == "table" and #v == 0 and type(dst[k]) == "table" then
      merge(dst[k], v)
    else
      dst[k] = v
    end
  end
end
merge(wasp, settings)

-- First match wins in wasp.keys, so these go in front of config.lua's.
wasp.keys = wasp.keys or {}
for i = #keys, 1, -1 do
  table.insert(wasp.keys, 1, keys[i])
end

return { settings = settings, keys = keys }
"""


def render_overrides(s: Settings) -> str:
    tree: dict = {}
    for spec in ALL_SPECS:  # spec order, so the file is stable
        if spec.path not in s.overrides():
            continue
        t = tree
        for k in spec.path[:-1]:
            t = t.setdefault(k, {})
        t[spec.path[-1]] = s.values[spec.path]
    keys = [entry_from_bind(b) for b in s.binds]
    return (_HEADER + "local settings = " + lua_literal(tree) + "\n\n"
            + "local keys = " + lua_literal(keys) + "\n" + _APPLY)


# ── config ───────────────────────────────────────────────────────────────
class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "config.lua"
        self.overrides_path = self.path.with_name(OVERRIDES_NAME)
        self.existed = self.path.exists()

    def _source(self) -> Path | None:
        """The file whose settings Kantele starts from."""
        if self.existed:
            return self.path
        return EXAMPLE if EXAMPLE.exists() else None

    def has_loader(self) -> bool:
        return self.existed and LOADER_MARK in self.path.read_text()

    def read(self) -> Settings:
        s = Settings()
        src = self._source()
        base = _run_lua(src, skip=True) if src else {}
        base = base if isinstance(base, dict) else {}
        for spec in ALL_SPECS:
            s.base[spec.path] = _coerce(spec, _get(base, spec.path))
        s.base_binds = [bind_from_entry(e) for e in base.get("keys") or []
                        if isinstance(e, dict)]
        s.values = dict(s.base)
        if self.overrides_path.exists():
            mine = _run_lua(self.overrides_path, skip=False, what="return") or {}
            settings = mine.get("settings") or {}
            for spec in ALL_SPECS:
                v = _get(settings, spec.path)
                if v is not None:
                    s.values[spec.path] = _coerce(spec, v)
            s.binds = [bind_from_entry(e) for e in mine.get("keys") or []
                       if isinstance(e, dict)]
        return s

    def save(self, s: Settings) -> Path | None:
        """Writes kantele.lua and makes sure config.lua loads it, then runs
        the result through Lua as a check. Returns the backup of config.lua
        made when its loader line is first added, if any."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if not self.existed:
            if not EXAMPLE.exists():
                raise LuaError(f"No {self.path} and no {EXAMPLE} to start from.")
            shutil.copy(EXAMPLE, self.path)
            self.existed = True
        text = self.path.read_text()
        if LOADER_MARK not in text:
            bak = self.path.with_name(self.path.name + ".kantele-bak")
            if not bak.exists():
                shutil.copy2(self.path, bak)
                backup = bak
            sep = "" if text.endswith("\n") or not text else "\n"
            _atomic_write(self.path, text + sep + "\n" + LOADER)

        new = render_overrides(s)
        old = self.overrides_path.read_text() if self.overrides_path.exists() else None
        if new != old:
            _atomic_write(self.overrides_path, new)
            try:
                _run_lua(self.path, skip=False)
            except LuaError:
                if old is None:
                    self.overrides_path.unlink()
                else:
                    _atomic_write(self.overrides_path, old)
                raise
        return backup


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".kantele-tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def validate(s: Settings) -> list[str]:
    errs: list[str] = []
    for spec in ALL_SPECS:
        v = s.values.get(spec.path)
        if spec.kind == "color" and not COLOR_RE.match(str(v)):
            errs.append(f"{spec.label}: '{v}' is not a #RRGGBB[AA] color.")
        elif spec.kind == "argv" and not v:
            errs.append(f"{spec.label} can't be empty.")
        elif spec.kind == "choice" and v not in spec.choices:
            errs.append(f"{spec.label}: '{v}' must be one of {', '.join(spec.choices)}.")
    seen: set[str] = set()
    for b in s.binds:
        combo = normalize_combo(b.combo)
        if not combo or not KEYSYM_RE.match(b.key):
            errs.append(f"Key '{b.combo}' is not like mod+shift+Return.")
            continue
        bad = [m for m in b.mods if m not in MOD_NAMES]
        if bad:
            errs.append(f"Key '{b.combo}': unknown modifier {', '.join(bad)} "
                        f"(use {', '.join(MOD_NAMES)}).")
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
    r = send_reload(NAME)
    if r == "absent":
        return "Saved. wasp isn't running; it will use the new settings next time it starts."
    if r == "unsupported":
        return ("Saved. This wasp can't reload on request (needs wasp 0.10.1 or newer): "
                "press mod+shift+r to apply.")
    return "Saved and applied."
