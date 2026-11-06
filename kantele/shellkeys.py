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
import os
import shutil
import sys
from pathlib import Path

from .backends import detect_running, spitfire, wasp
from .backends.luautil import LuaError

# key -> kantele-shell verb. Free in the example config.lua of both compositors.
KEYS = {
    "p": "launcher",
    "z": "lock",
    "n": "dashboard",
    "x": "session",
    "y": "wallpaper",
    "a": "ai",
}

BACKENDS = {
    "wasp": (wasp, "super+{}"),
    "spitfire": (spitfire, "Mod4+{}"),
}
FILES = ("config.lua", "kantele.lua")


def kantele_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "kantele"


def _copy_existing(src_dir: Path, dst: Path) -> None:
    """Copies FILES into a new dst, in one step, so dst is never left half done."""
    tmp = dst.with_name(dst.name + ".kantele-tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name in FILES:
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
        _copy_existing(config.path.parent, backup)
        messages.append(f"Backup of your files: {backup}")

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
            messages.append(f"{combo}: kept your own Kantele binding, not {verb}.")

    errors = backend.validate(settings)
    if errors:
        raise LuaError("\n".join(errors))
    config.save(settings)
    _copy_existing(config.path.parent, kantele_dir() / "applied" / wm)

    messages.append(f"Added {len(added)} keys." if added else "Nothing to add.")
    messages.append(backend.reload_running())
    return messages


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
