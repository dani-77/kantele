"""Command-line entry point. Qt is only imported for the GUI, so subcommands work
without a display."""

from __future__ import annotations

import sys


def main() -> None:
    if sys.argv[1:2] == ["shell-keys"]:
        from .shellkeys import main as shell_keys
        sys.exit(shell_keys(sys.argv[2:]))
    if sys.argv[1:2] == ["shell-setup"]:
        from .shellkeys import setup_main
        sys.exit(setup_main(sys.argv[2:]))
    from .app import main as gui
    gui()
