"""The Shell tab's logic and, when Qt is available, the tab itself."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kantele import shellctl
from kantele.backends import wasp

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from kantele.ui import luapage
except ImportError:
    QApplication = None

CONFIG = 'wasp = {}\nwasp.keys = {}\nwasp.bar = { enable = true }\n'


class ConfigStartsAShellTest(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.lua"
            path.write_text(text)
            return shellctl.config_starts_a_shell(path)

    def test_every_way_of_starting_one(self):
        for line in ('{ "qsd77", "run", "-c", "utumno" },',
                     '{ "sh", "-c", "qsd77 run -c utumno" },',
                     '"qsd77 run -c quickshell-d77",',
                     '{ "qs", "-c", "utumno" },',
                     '{ "fabric-d77" },',
                     '"helium-shell",'):
            self.assertTrue(self.check(line), line)

    def test_what_is_not_starting_one(self):
        for line in ('-- { "qsd77", "run", "-c", "utumno" },',
                     '{ "dunst" }, -- not fabric-d77',
                     'bind({ "super" }, "t", "spawn", { cmd = { "qsd77", "-c", "utumno", "locker" } })',
                     'bind({ "super" }, "p", "spawn", { cmd = { "fabric-d77-signal", "USR1" } })',
                     '{ "swayidle", "-w", "timeout", "300", "kantele-shell lock" },'):
            self.assertFalse(self.check(line), line)

    def test_a_missing_file(self):
        self.assertFalse(shellctl.config_starts_a_shell(Path("/nonexistent/config.lua")))


@unittest.skipUnless(shutil.which(wasp.LUA), "needs lua5.4")
class ChooseTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        for patcher in (
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home),
                                         "XDG_CURRENT_DESKTOP": "sway"}),
            mock.patch.object(wasp, "reload_running", return_value="Saved."),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        (self.home / "wasp").mkdir()
        (self.home / "wasp/config.lua").write_text(CONFIG)

    def test_choose_for_the_next_login_and_back(self):
        path = ("bar", "enable")
        shellctl.choose("wasp", "fabric-d77")
        self.assertEqual(shellctl.chosen("wasp"), "fabric-d77")
        settings = wasp.Config().read()
        self.assertTrue(settings.shell_autostart)
        self.assertIs(settings.values[path], False)

        shellctl.choose("wasp", "")
        self.assertEqual(shellctl.chosen("wasp"), "")
        settings = wasp.Config().read()
        self.assertFalse(settings.shell_autostart)
        self.assertIs(settings.values[path], True)

    def test_each_compositor_keeps_its_own(self):
        shellctl.choice_file("spitfire").parent.mkdir(parents=True, exist_ok=True)
        shellctl.choice_file("spitfire").write_text("utumno\n")
        shellctl.choose("wasp", "fabric-d77")
        self.assertEqual(shellctl.chosen("spitfire"), "utumno")
        self.assertEqual(shellctl.chosen("wasp"), "fabric-d77")

    def test_an_unknown_name_in_the_file_counts_as_none(self):
        shellctl.choice_file("wasp").parent.mkdir(parents=True, exist_ok=True)
        shellctl.choice_file("wasp").write_text("noctalia\n")
        self.assertEqual(shellctl.chosen("wasp"), "")

    @unittest.skipIf(QApplication is None, "needs PyQt6")
    def test_tab_outside_the_session(self):
        app = QApplication.instance() or QApplication([])
        (self.home / "wasp/config.lua").write_text(CONFIG + '-- x\nwasp.autostart = { { "fabric-d77" } }\n')
        page = luapage.WaspPage()
        tab = dict(page.parts)["Shell"]
        self.assertFalse(tab.apply_button.isEnabled())
        self.assertFalse(tab.back_button.isEnabled())
        self.assertIn("next login", tab.state.text())
        self.assertIn("config.lua also starts", tab.warning.text())
        self.assertEqual(tab.selected(), "")

        with mock.patch.object(shellctl, "installed", return_value=True):
            tab.combo.setCurrentIndex(tab.combo.findData("utumno"))
        tab.use_next_login()
        self.assertEqual(shellctl.chosen("wasp"), "utumno")
        self.assertEqual(dict(page.parts)["Shell"].selected(), "utumno")
        self.assertTrue(wasp.Config().read().shell_autostart)
        page.deleteLater()
        app.processEvents()

    @unittest.skipIf(QApplication is None, "needs PyQt6")
    def test_saving_the_page_keeps_the_autostart(self):
        app = QApplication.instance() or QApplication([])
        shellctl.choose("wasp", "fabric-d77")
        page = luapage.WaspPage()
        self.assertIsNotNone(page.save(False))
        self.assertTrue(wasp.Config().read().shell_autostart)
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
