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
