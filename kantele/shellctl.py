"""What the Shell tab needs from the system: which d77 shells are installed, which
one a compositor uses, and running `kantele-shell`. No Qt here."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .shellkeys import BACKENDS, kantele_dir, setup

# name -> what the user sees.
SHELLS = {
    "utumno": "Utumno",
    "fabric-d77": "fabric-d77",
    "helium-d77": "helium-d77",
    "frost-d77": "Frost",
    "atg": "ATG",
}
# The display server each shell runs on. Wayland compositors (wasp, spitfire,
# whiplash) use the Wayland shells; X11 window managers (wmd77, whiplash's X11
# backend) use ATG.
BACKEND = {"utumno": "wayland", "fabric-d77": "wayland", "helium-d77": "wayland",
           "frost-d77": "wayland", "atg": "x11"}
BACKENDS_ORDER = ("wayland", "x11")
KEEP_SECONDS = 15

# What to install for each shell. On Void the shell packages leave quickshell out
# on purpose, so it doesn't hold back system upgrades; on Arch they depend on it.
VOID_PACKAGES = {
    "utumno": ["quickshell", "qsd77", "utumno"],
    "fabric-d77": ["fabric-d77"],
    "helium-d77": ["helium-d77"],
    "frost-d77": ["frost-d77"],
    "atg": ["quickshell", "qsd77", "atg"],
}
# ATG isn't in the AUR yet, so Arch has no packages for it.
ARCH_PACKAGES = {
    "utumno": ["qsd77", "utumno"],
    "fabric-d77": ["fabric-d77"],
    "helium-d77": ["helium-d77"],
    "frost-d77": ["frost-d77"],
}
# quickshell-d77 is archived and Utumno carries everything it had: a choice saved
# before that means Utumno.
RENAMED = {"quickshell-d77": "utumno"}
AUR_HELPERS = ("paru", "yay")
# How each terminal runs a command given after this prefix.
TERMINALS = {"foot": ["foot"], "kitty": ["kitty"], "alacritty": ["alacritty", "-e"],
             "xterm": ["xterm", "-e"]}


class CantInstall(Exception):
    """Why this system can't install a shell, in words for the user."""


def shells_for(backend: str) -> dict[str, str]:
    """SHELLS, only those that run on `backend` ("wayland" or "x11")."""
    return {name: label for name, label in SHELLS.items() if BACKEND[name] == backend}

# How a config.lua would start one of the shells by itself, once comments are gone.
_STARTS_SHELL = re.compile(
    r"""qsd77["',\s]+run|\bqs["',\s]+-c\b|\bfabric-d77\b(?!-signal)|\bhelium-shell\b|\bfrost["',\s]+run\b"""
    # ATG as whiplash-session and wmd77's startup.sh start it: qs -n -d -c atg
    r"""|\bqs\b(?:\s+-\S+)*\s+(?:-c|--config)[\s=]atg\b""")


def installed(shell: str) -> bool:
    if shell == "utumno":
        return Path(f"/usr/share/quickshell/{shell}").is_dir() and bool(shutil.which("qsd77"))
    if shell == "fabric-d77":
        return bool(shutil.which("fabric-d77"))
    if shell == "helium-d77":
        return bool(shutil.which("helium-shell") and shutil.which("helium-osd"))
    if shell == "frost-d77":
        return bool(shutil.which("frost"))
    if shell == "atg":
        return (Path("/usr/share/quickshell/atg/shell.qml").is_file()
                and bool(shutil.which("qs") and shutil.which("qsd77")))
    return False


def install_command(shell: str) -> list[str]:
    """The command that installs `shell` here. On Void, pkexec asks for the password.
    On Arch, the AUR helper asks its own questions, so it gets a terminal."""
    if shutil.which("xbps-install"):
        if not shutil.which("pkexec"):
            raise CantInstall("Installing needs pkexec (polkit).")
        return ["pkexec", "xbps-install", "-Sy", *VOID_PACKAGES[shell]]
    if shutil.which("pacman"):
        if shell not in ARCH_PACKAGES:
            raise CantInstall(f"{SHELLS[shell]} isn't packaged for Arch yet.")
        helper = next((h for h in AUR_HELPERS if shutil.which(h)), None)
        if not helper:
            raise CantInstall("These packages are in the AUR, which needs paru or yay. "
                              f"Or install by hand: {' '.join(ARCH_PACKAGES[shell])}")
        terminal = next((t for t in TERMINALS if shutil.which(t)), None)
        if not terminal:
            raise CantInstall(f"No terminal found. Run: {helper} -S "
                              f"{' '.join(ARCH_PACKAGES[shell])}")
        script = ('"$@"; echo; printf "Press Enter to close. "; read -r _')
        return [*TERMINALS[terminal], "sh", "-c", script, "kantele-install",
                helper, "-S", *ARCH_PACKAGES[shell]]
    raise CantInstall("Installing a shell from here only works on Void and Arch.")


def command() -> str:
    """kantele-shell on PATH, or next to this package when run from a checkout."""
    found = shutil.which("kantele-shell")
    if found:
        return found
    return str(Path(__file__).resolve().parent.parent / "kantele-shell")


def choice_file(wm: str, backend: str = "wayland") -> Path:
    """Where kantele-shell keeps the choice: shell-<wm> for Wayland and
    shell-<wm>-x11 for X11, so whiplash's two backends never share one."""
    suffix = "-x11" if backend == "x11" else ""
    return kantele_dir() / f"shell-{wm}{suffix}"


def chosen(wm: str, backend: str = "wayland") -> str:
    """The shell chosen for `wm` on `backend`, or "" for whatever it came with."""
    try:
        name = choice_file(wm, backend).read_text().strip()
    except OSError:
        return ""
    name = RENAMED.get(name, name)
    return name if BACKEND.get(name) == backend else ""


def choose(wm: str, shell: str, backend: str = "wayland") -> list[str]:
    """Makes `shell` start with `wm` from the next login, without touching what's
    running. An empty name goes back to what the compositor came with."""
    if shell and BACKEND.get(shell) != backend:
        raise ValueError(f"{shell} doesn't run on {backend}")
    path = choice_file(wm, backend)
    if shell:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(shell + "\n")
        return setup(wm, autostart="on", bar="off", backend=backend)
    path.unlink(missing_ok=True)
    return setup(wm, autostart="off", bar="default", backend=backend)


def is_running_session(wm: str, backend: str = "wayland") -> bool:
    """True when Kantele runs inside a `wm` session on `backend`. X11 asks
    kantele-shell: wmd77 started by startx sets no XDG_CURRENT_DESKTOP."""
    if backend == "wayland":
        return (os.environ.get("XDG_CURRENT_DESKTOP") == wm
                and os.environ.get("XDG_SESSION_TYPE") != "x11")
    st = status()
    return st.get("compositor") == wm and st.get("session") == "x11"


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
    comment = "#" if path.suffix == ".toml" else "--"
    code = (line.split(comment, 1)[0] for line in lines)
    return any(_STARTS_SHELL.search(line) for line in code)


def _autostart(settings, backend: str) -> list[str]:
    if hasattr(settings, "autostart_for"):
        return settings.autostart_for(backend) or []
    return settings.autostart or []


def wmd77_startup_script() -> Path:
    """The startup script wmd77 runs, from its config.toml."""
    from .backends import pwm
    settings = pwm.Config(flavor=pwm.WMD77).read()
    script = settings.apps.get("startup_script") or pwm.WMD77.apps["startup_script"]
    return Path(os.path.expanduser(str(script)))


def startup_script_starts_a_shell(path: Path) -> bool:
    """True if a startup script starts a shell by itself, instead of through
    `kantele-shell start` (which may fall back to starting ATG itself, as the
    d77void one does: that's fine)."""
    try:
        text = path.read_text()
    except OSError:
        return False
    code = [line.split("#", 1)[0] for line in text.splitlines()]
    if any("kantele-shell start" in line for line in code):
        return False
    return any(_STARTS_SHELL.search(line) for line in code)


def autostart_shells(wm: str, backend: str = "wayland") -> list[str]:
    """The autostart entries that start a shell by themselves on `backend`, for a
    compositor whose autostart list Kantele edits (whiplash's config.toml).
    Always empty for the others: their config.lua is the user's, so Kantele only
    warns there."""
    module = BACKENDS.get(wm, (None,))[0]
    if module is None or not getattr(module, "AUTOSTART_IN_CONFIG", False):
        return []
    return [c for c in _autostart(module.Config().read(), backend) if _STARTS_SHELL.search(c)]


def drop_autostart_shells(wm: str, backend: str = "wayland") -> list[str]:
    """Takes out of `backend`'s autostart the entries autostart_shells() finds,
    so they don't start in place of the chosen shell. Returns what was taken
    out. In a list both backends share, such a line is wrong on one of them
    anyway (Utumno under X11, ATG under Wayland), so it goes from there too."""
    found = autostart_shells(wm, backend)
    if found:
        module = BACKENDS[wm][0]
        config = module.Config()
        settings = config.read()
        kept = [c for c in _autostart(settings, backend) if c not in found]
        own = getattr(settings, "backend_autostart", {}).get(backend)
        if own is not None:
            settings.backend_autostart[backend] = kept
        else:
            settings.autostart = kept
        config.save(settings)
    return found
