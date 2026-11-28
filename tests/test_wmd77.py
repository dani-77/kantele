import tempfile
import tomllib
import unittest
from pathlib import Path

from kantele.backends import pwm

SAMPLE = """\
# my wmd77 config
[theme]
active = "dracula"

[bar]
enable = false   # polybar instead
reserve_top = 30

[[bind]]
key = "M-r"
action = "spawn"
arg = "d77run"
"""


class Wmd77BackendTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.toml"
        self.path.write_text(SAMPLE)

    def tearDown(self):
        self.dir.cleanup()

    def test_read_bar(self):
        s = pwm.Config(self.path, pwm.WMD77).read()
        self.assertEqual(s.bar, {"enable": False, "reserve_top": 30})
        self.assertIsNone(s.bar_widgets)
        self.assertEqual(s.theme, "dracula")
        self.assertEqual(s.binds[0].arg, "d77run")

    def test_noop_save_is_identical(self):
        c = pwm.Config(self.path, pwm.WMD77)
        c.apply(c.read())
        c.save()
        self.assertEqual(self.path.read_text(), SAMPLE)

    def test_write_bar_keeps_comments(self):
        c = pwm.Config(self.path, pwm.WMD77)
        s = c.read()
        s.bar = {"enable": True, "position": "bottom", "height": 24}
        self.assertEqual(pwm.validate(s, pwm.WMD77), [])
        c.apply(s)
        c.save()
        text = self.path.read_text()
        self.assertIn("# my wmd77 config", text)
        self.assertEqual(tomllib.loads(text)["bar"],
                         {"enable": True, "position": "bottom", "height": 24})

    def test_validate_bar(self):
        s = pwm.Config(self.path, pwm.WMD77).read()
        s.bar = {"position": "left", "height": 3, "reserve_top": 9000}
        errs = "\n".join(pwm.validate(s, pwm.WMD77))
        self.assertIn("top or bottom", errs)
        self.assertIn("height must be between", errs)
        self.assertIn("reserve top must be between", errs)

    def test_pwm_config_ignores_wmd77_bar_keys(self):
        c = pwm.Config(self.path, pwm.PWM)
        s = c.read()
        self.assertEqual(s.bar, {})
        c.apply(s)
        c.save()
        self.assertEqual(self.path.read_text(), SAMPLE)

    def test_paths_and_defaults(self):
        self.assertEqual(pwm.config_path(pwm.WMD77).parts[-2:], ("wmd77", "config.toml"))
        self.assertEqual(pwm.WMD77.apps["startup_script"], "/etc/xdg/wmd77/startup.sh")
        self.assertEqual(pwm.WMD77.window_rules, [])


if __name__ == "__main__":
    unittest.main()


try:
    import os
    from unittest import mock
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from kantele import shellctl
    from kantele.ui import pwm as pwm_ui
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "needs PyQt6")
class Wmd77ShellTabTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "wmd77").mkdir()
        self.cfg = self.home / "wmd77/config.toml"
        self.script = self.home / "startup.sh"
        self.cfg.write_text(f'[apps]\nstartup_script = "{self.script}"\n\n[bar]\nheight = 22\n')
        self.script.write_text("dunst &\n")
        for patcher in (
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home)}),
            mock.patch.object(shellctl, "status", return_value={}),
            mock.patch.object(shellctl, "installed", return_value=True),
            mock.patch.object(pwm, "reload_running", return_value="Saved."),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = QApplication.instance() or QApplication([])

    def tab(self):
        page = pwm_ui.Wmd77Page(self.cfg)
        self.addCleanup(self.app.processEvents)
        self.addCleanup(page.deleteLater)
        return dict(page.parts)["Shell"]

    def test_offers_atg_only(self):
        tab = self.tab()
        self.assertEqual([tab.combo.itemData(i) for i in range(tab.combo.count())], ["", "atg"])
        self.assertEqual(tab.warning.text(), "")

    def test_atg_turns_the_bar_off_with_room_for_it(self):
        tab = self.tab()
        tab.combo.setCurrentIndex(tab.combo.findData("atg"))
        tab.use_next_login()
        self.assertEqual(shellctl.chosen("wmd77", "x11"), "atg")
        bar = tomllib.loads(self.cfg.read_text())["bar"]
        self.assertEqual(bar, {"height": 22, "enable": False, "reserve_top": 48})

        tab = self.tab()
        tab.combo.setCurrentIndex(0)
        tab.use_next_login()
        self.assertEqual(shellctl.chosen("wmd77", "x11"), "")
        self.assertEqual(tomllib.loads(self.cfg.read_text())["bar"], {"height": 22})

    def test_warns_when_startup_sh_starts_atg_itself(self):
        self.script.write_text("QT_QPA_PLATFORM=xcb qs -n -d -c atg\n")
        tab = self.tab()
        self.assertIn("starts a shell by itself", tab.warning.text())
        self.assertIn("kantele-shell start", tab.warning.text())
