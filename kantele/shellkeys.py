"""`kantele shell-keys`: puts the common shell keybindings in kantele.lua.

Every key runs `kantele-shell <verb>`, so the same keys do the same thing on any
compositor and with any shell. They stay ordinary Kantele bindings, which you can
change or disable on the Keybindings page; a key you already bound in Kantele is
left alone.

The first time this runs for a compositor, config.lua and kantele.lua are copied
to ~/.config/kantele/pre-shell/<wm>/. `kantele-shell reset` puts them back. What
this command wrote is kept in ~/.config/kantele/applied/<wm>/, which lets reset
tell whether the files were changed afterwards and ask before replacing them.

This module must not import Qt: it runs without a display.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .backends import detect_running, pwm, spitfire, wasp, whiplash
from .backends.luautil import LuaError

# key -> kantele-shell verb. Free in the example config.lua of both compositors.
KEYS = {
    "p": "launcher",
    "z": "lock",
    "n": "dashboard",
    "x": "session",
    "y": "wallpaper",
    "a": "ai",
    "shift+z": "restore",  # the way out of a shell that came up broken
}

BACKENDS = {
    "wasp": (wasp, "super+{}"),
    "spitfire": (spitfire, "Mod4+{}"),
    "whiplash": (whiplash, "Super+{}"),
}
FILES = ("config.lua", "kantele.lua")


def _files(backend) -> tuple[str, ...]:
    """The files `shell-keys` backs up: whiplash keeps everything in config.toml."""
    return getattr(backend, "SHELL_FILES", FILES)


def kantele_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "kantele"


def _copy_existing(src_dir: Path, dst: Path, files: tuple[str, ...] = FILES) -> None:
    """Copies FILES into a new dst, in one step, so dst is never left half done."""
    tmp = dst.with_name(dst.name + ".kantele-tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name in files:
        if (src_dir / name).exists():
            shutil.copy2(src_dir / name, tmp / name)
    shutil.rmtree(dst, ignore_errors=True)
    os.replace(tmp, dst)


def _base_combo(backend, bind, settings) -> str:
    """config.lua's combo as Kantele's own bindings would spell it: wasp's "mod"
    is an alias for whichever key wasp.modkey names."""
    combo = bind.combo
    if backend is wasp:
        modkey = str(settings.values.get(("modkey",), ""))
        combo = "+".join(modkey if part == "mod" else part for part in combo.split("+"))
    return backend.normalize_combo(combo)


def apply(wm: str) -> list[str]:
    """Adds the keys for `wm`, backing up first. Returns what to tell the user."""
    backend, pattern = BACKENDS[wm]
    config = backend.Config()
    settings = config.read()
    messages = []

    backup = kantele_dir() / "pre-shell" / wm
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        _copy_existing(config.path.parent, backup, _files(backend))
        messages.append(f"Backup of your files: {backup}")
    if settings.binds is None:
        # whiplash without a [keybinds] table: its built-in keys are the base,
        # and a table with only the new keys would drop all of them.
        settings.binds = settings.effective_binds()

    existing = {backend.normalize_combo(b.combo): b for b in settings.binds}
    base = {_base_combo(backend, b, settings) for b in settings.base_binds}
    added = []
    for key, verb in KEYS.items():
        combo = backend.normalize_combo(pattern.format(key))
        command = f"kantele-shell {verb}"
        current = existing.get(combo)
        if current is None:
            settings.binds.append(backend.Bind(combo, "spawn", command))
            added.append(combo)
            if combo in base:
                messages.append(f"{combo}: replaces the binding from config.lua.")
        elif current.action != "spawn" or current.arg != command:
            if getattr(backend, "SHELL_KEYS_REPLACE", False):
                was = " ".join(p for p in (current.action, current.arg) if p)
                current.action, current.arg = "spawn", command
                added.append(combo)
                messages.append(f"{combo}: replaces '{was}'.")
            else:
                messages.append(f"{combo}: kept your own Kantele binding, not {verb}.")

    errors = backend.validate(settings)
    if errors:
        raise LuaError("\n".join(errors))
    config.save(settings)
    _copy_existing(config.path.parent, kantele_dir() / "applied" / wm, _files(backend))

    messages.append(f"Added {len(added)} keys." if added else "Nothing to add.")
    messages.append(backend.reload_running())
    return messages


def setup(wm: str, autostart: str | None = None, bar: str | None = None,
          backend: str = "wayland") -> list[str]:
    """Changes what `kantele-shell` needs from kantele.lua: whether it adds
    `kantele-shell start` to the autostart, and the built-in bar ("on", "off", or
    "default" for config.lua's value). `backend` is the display server the shell
    runs on: "x11" for whiplash's X11 session and for wmd77."""
    profile = backend
    if wm == "wmd77" and profile == "x11":
        return _setup_wmd77(bar)
    module = BACKENDS.get(wm, (None,))[0]
    if module is None or (profile == "x11" and not getattr(module, "X11", False)):
        raise LuaError(f"Setting up an X11 shell for {wm} isn't supported yet.")
    backend = module
    config = backend.Config()
    settings = config.read()
    if autostart is not None:
        if hasattr(settings, "set_shell_autostart"):
            # Is a shell chosen for the other backend? Then turning this one off
            # must leave `kantele-shell start` where that one runs it.
            other = "wayland" if profile == "x11" else "x11"
            suffix = "-x11" if other == "x11" else ""
            choice = kantele_dir() / f"shell-{wm}{suffix}"
            try:
                other_wants_it = bool(choice.read_text().strip())
            except OSError:
                other_wants_it = False
            settings.set_shell_autostart(autostart == "on", profile, other_wants_it)
        else:
            settings.shell_autostart = autostart == "on"
    if bar is not None and getattr(backend, "HAS_BAR", True):
        path = ("bar", "enable")
        settings.values[path] = settings.base[path] if bar == "default" else bar == "on"
    errors = backend.validate(settings)
    if errors:
        raise LuaError("\n".join(errors))
    config.save(settings)
    return [backend.reload_running()]


# ATG's bar: 40 px plus an 8 px top margin.
ATG_RESERVE_TOP = 48
_WMD77_BAR_KEYS = ("enable", "reserve_top")


def _setup_wmd77(bar: str | None) -> list[str]:
    """wmd77 starts its shell from startup.sh, which is the user's, so only the
    bar is Kantele's to change: off, with room kept for ATG, while ATG is the
    shell; back to what config.toml had before ("default"); or on, when no shell
    could start. wmd77 restarts to apply it (since 0.5.4 without running
    startup.sh again)."""
    if bar is None:
        return []
    config = pwm.Config(flavor=pwm.WMD77)
    settings = config.read()
    saved = kantele_dir() / "wmd77-bar.previous"
    previous: dict[str, object] = {}
    try:
        previous = json.loads(saved.read_text())
    except (OSError, ValueError):
        pass

    def restore() -> None:
        for key in _WMD77_BAR_KEYS:
            if previous.get(key) is None:
                settings.bar.pop(key, None)
            else:
                settings.bar[key] = previous[key]

    if bar == "off":
        if not saved.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(json.dumps({k: settings.bar.get(k) for k in _WMD77_BAR_KEYS}) + "\n")
        settings.bar["enable"] = False
        settings.bar["reserve_top"] = ATG_RESERVE_TOP
    elif bar == "default":
        restore()
        saved.unlink(missing_ok=True)
    else:  # "on": no shell, so the built-in bar with the room it had before
        restore()
        settings.bar["enable"] = True
    errors = pwm.validate(settings, pwm.WMD77)
    if errors:
        raise LuaError("\n".join(errors))
    config.apply(settings)
    config.save()
    return [pwm.reload_running(pwm.WMD77)]


def setup_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="kantele shell-setup",
        description="Change the autostart entry and built-in bar for kantele-shell.",
    )
    parser.add_argument("--wm", choices=sorted({*BACKENDS, "wmd77"}), required=True)
    parser.add_argument("--backend", choices=("wayland", "x11"), default="wayland")
    parser.add_argument("--autostart", choices=("on", "off"))
    parser.add_argument("--bar", choices=("on", "off", "default"))
    args = parser.parse_args(argv)
    try:
        messages = setup(args.wm, args.autostart, args.bar, args.backend)
    except (LuaError, OSError) as error:
        print(f"kantele shell-setup: {error}", file=sys.stderr)
        return 1
    print("\n".join(messages))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="kantele shell-keys",
        description="Add the common shell keybindings to the compositor's kantele.lua.",
    )
    parser.add_argument("--wm", choices=sorted(BACKENDS),
                        help="compositor to configure (default: the running one)")
    args = parser.parse_args(argv)

    wm = args.wm or detect_running(BACKENDS)
    if not wm:
        print("kantele shell-keys: no supported compositor running; use --wm.",
              file=sys.stderr)
        return 2
    try:
        messages = apply(wm)
    except (LuaError, OSError) as error:
        print(f"kantele shell-keys: {error}", file=sys.stderr)
        return 1
    print("\n".join(messages))
    return 0
