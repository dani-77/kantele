"""Per-window-manager backends: read, validate and write each WM's config."""

from __future__ import annotations

import os
import signal
from pathlib import Path


def detect_running(supported) -> str | None:
    """Name of a supported window manager running for this user, if any."""
    uid = os.getuid()
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            comm = (p / "comm").read_text().strip()
            if comm in supported and p.stat().st_uid == uid:
                return comm
        except OSError:
            continue
    return None


def running_pids(name: str) -> list[int]:
    """PIDs of this user's processes whose command name is `name`."""
    uid = os.getuid()
    pids = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if (p / "comm").read_text().strip() == name and p.stat().st_uid == uid:
                pids.append(int(p.name))
        except OSError:
            continue
    return pids


def catches_sighup(pid: int) -> bool:
    """True if `pid` installed a SIGHUP handler. Without one, SIGHUP's default
    action would kill the window manager and the whole session with it."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("SigCgt:"):
                return bool(int(line.split()[1], 16) & (1 << (signal.SIGHUP - 1)))
    except OSError:
        pass
    return False


def send_reload(name: str) -> str:
    """Sends SIGHUP to every running `name` that handles it. Returns
    "absent" (not running), "unsupported" (some instance has no handler;
    nothing was sent) or "sent"."""
    pids = running_pids(name)
    if not pids:
        return "absent"
    if not all(catches_sighup(p) for p in pids):
        return "unsupported"
    for p in pids:
        os.kill(p, signal.SIGHUP)
    return "sent"
