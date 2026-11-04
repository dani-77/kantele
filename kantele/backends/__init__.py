"""Per-window-manager backends: read, validate and write each WM's config."""

from __future__ import annotations

import os
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
