"""Command-line entry point. Qt is only imported for the GUI, so subcommands work
without a display."""

from __future__ import annotations

import sys


def main() -> None:
    if sys.argv[1:2] == ["shell-keys"]:
        from .shellkeys import main as shell_keys
        sys.exit(shell_keys(sys.argv[2:]))
    from .app import main as gui
    gui()
