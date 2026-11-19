"""Kantele main window: one page per supported window manager."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QMainWindow, QPushButton, QStatusBar,
    QVBoxLayout, QWidget,
)

from . import __version__
from .backends import detect_running
from .ui.pwm import PwmPage, Wmd77Page
from .ui.luapage import SpitfirePage, WaspPage
from .ui.whiplash import WhiplashPage

PAGES = {"pwm": PwmPage, "spitfire": SpitfirePage, "wasp": WaspPage, "whiplash": WhiplashPage,
         "wmd77": Wmd77Page}


def pick_wm() -> str | None:
    """The supported WM running for this user, or the session's desktop name."""
    found = detect_running(PAGES)
    if found:
        return found
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return desktop if desktop in PAGES else None


def app_icon() -> QIcon:
    """The installed theme icon, or the repo's logo when run from a checkout."""
    if QIcon.hasThemeIcon("kantele"):
        return QIcon.fromTheme("kantele")
    logo = Path(__file__).resolve().parent.parent / "assets" / "kantele.png"
    return QIcon(str(logo)) if logo.exists() else QIcon.fromTheme("preferences-desktop")


class MainWindow(QMainWindow):
    def __init__(self, wm: str, path=None):
        super().__init__()
        self.setWindowTitle(f"Kantele — {wm}")
        self.setWindowIcon(app_icon())
        self.page = PAGES[wm](path)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.page)
        row = QHBoxLayout()
        revert = QPushButton("Revert")
        save = QPushButton("Save")
        apply = QPushButton("Save and apply")
        apply.setDefault(True)
        revert.clicked.connect(self._revert)
        save.clicked.connect(lambda: self._save(False))
        apply.clicked.connect(lambda: self._save(True))
        row.addWidget(revert)
        row.addStretch()
        row.addWidget(save)
        row.addWidget(apply)
        lay.addLayout(row)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.resize(960, 720)

    def _revert(self) -> None:
        self.page.reload()
        self.statusBar().showMessage("Reloaded from disk.", 5000)

    def _save(self, apply: bool) -> None:
        msg = self.page.save(apply)
        if msg:
            self.statusBar().showMessage(msg, 15000)


def main() -> None:
    ap = argparse.ArgumentParser(prog="kantele",
                                 description="Tune your window manager, string by string.")
    ap.add_argument("--wm", choices=sorted(PAGES),
                    help="window manager to configure (default: the running one)")
    ap.add_argument("--config", help="config file to edit instead of the default")
    ap.add_argument("--version", action="version", version=f"kantele {__version__}")
    args = ap.parse_args()

    wm = args.wm or pick_wm()
    if wm is None:
        # Never fall back to some other WM's config silently: editing a file the
        # session doesn't use would look like settings that do nothing.
        desktop = os.environ.get("XDG_CURRENT_DESKTOP") or "this session"
        print(f"kantele: {desktop} isn't supported; pick one with --wm "
              f"({', '.join(sorted(PAGES))}).", file=sys.stderr)
        sys.exit(2)
    app = QApplication(sys.argv)
    app.setApplicationName("kantele")
    app.setDesktopFileName("kantele")
    app.setWindowIcon(app_icon())
    w = MainWindow(wm, args.config)
    w.show()
    sys.exit(app.exec())
