"""What the Shell tab needs from the system: which d77 shells are installed, which
one a compositor uses, and running `kantele-shell`. No Qt here."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .shellkeys import kantele_dir, setup

# name -> what the user sees.
SHELLS = {
    "quickshell-d77": "quickshell-d77",
    "utumno": "Utumno",
    "fabric-d77": "fabric-d77",
    "helium-d77": "helium-d77",
}
KEEP_SECONDS = 15

# How a config.lua would start one of the shells by itself, once comments are gone.
_STARTS_SHELL = re.compile(
    r"""qsd77["',\s]+run|\bqs["',\s]+-c\b|\bfabric-d77\b(?!-signal)|\bhelium-shell\b""")


def installed(shell: str) -> bool:
    if shell in ("quickshell-d77", "utumno"):
        return Path(f"/usr/share/quickshell/{shell}").is_dir() and bool(shutil.which("qsd77"))
    if shell == "fabric-d77":
        return bool(shutil.which("fabric-d77"))
    if shell == "helium-d77":
        return bool(shutil.which("helium-shell") and shutil.which("helium-osd"))
    return False


def command() -> str:
    """kantele-shell on PATH, or next to this package when run from a checkout."""
    found = shutil.which("kantele-shell")
    if found:
        return found
    return str(Path(__file__).resolve().parent.parent / "kantele-shell")


def choice_file(wm: str) -> Path:
    return kantele_dir() / f"shell-{wm}"


def chosen(wm: str) -> str:
    """The shell chosen for `wm`, or "" for whatever the compositor came with."""
    try:
        name = choice_file(wm).read_text().strip()
    except OSError:
        return ""
    return name if name in SHELLS else ""


def choose(wm: str, shell: str) -> list[str]:
    """Makes `shell` start with `wm` from the next login, without touching what's
    running. An empty name goes back to what the compositor came with."""
    if shell:
        choice_file(wm).parent.mkdir(parents=True, exist_ok=True)
        choice_file(wm).write_text(shell + "\n")
        return setup(wm, autostart="on", bar="off")
    choice_file(wm).unlink(missing_ok=True)
    return setup(wm, autostart="off", bar="default")


def is_running_session(wm: str) -> bool:
    return os.environ.get("XDG_CURRENT_DESKTOP") == wm


def status() -> dict[str, str]:
    """`kantele-shell status` for the session this runs in, or {} if it can't say."""
    try:
        done = subprocess.run([command(), "status"], capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if done.returncode != 0:
        return {}
    pairs = (line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
    return dict(pairs)


def config_starts_a_shell(path: Path) -> bool:
    """True if config.lua starts a shell by itself. It would run next to the chosen
    one, or stop it from starting, so Kantele warns instead of editing the file."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return False
    code = (line.split("--", 1)[0] for line in lines)
    return any(_STARTS_SHELL.search(line) for line in code)
