import tempfile
import tomllib
import unittest
from pathlib import Path

from kantele.backends import pwm

SAMPLE = """\
# my pwm config
[theme]
active = "dracula"  # favourite

[apps]
terminal = "st"

# floats
[[float_rule]]
class = "d77run"
width_ratio = 0.4

[bar]
widgets = [
    "workspaces", "clock",
]

[[bind]]
key = "M-r"
action = "spawn"
arg = "d77run"

[keyboard]
layout = "pt"  # home
options = ["caps:escape", "compose:ralt"]
repeat_rate = 40
"""


class PwmBackendTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.toml"
        self.path.write_text(SAMPLE)

    def tearDown(self):
        self.dir.cleanup()

    def test_read(self):
        s = pwm.Config(self.path).read()
        self.assertEqual(s.theme, "dracula")
        self.assertEqual(s.apps, {"terminal": "st"})
        self.assertEqual(s.bar_widgets, ["workspaces", "clock"])
        self.assertEqual(s.binds, [pwm.Bind("M-r", "spawn", "d77run")])
        self.assertEqual(s.float_rules, [pwm.FloatRule("d77run", 0.4, None)])
        self.assertEqual(s.keyboard, {"layout": "pt", "options": "caps:escape,compose:ralt",
                                      "repeat_rate": 40})

    def test_noop_save_is_byte_identical(self):
        c = pwm.Config(self.path)
        c.apply(c.read())
        c.save()
        self.assertEqual(self.path.read_text(), SAMPLE)

    def test_edit_keeps_comments_and_parses(self):
        c = pwm.Config(self.path)
        s = c.read()
        s.apps["terminal"] = "alacritty"
        s.binds.append(pwm.Bind("M-Up", "inc_main", "2"))
        s.float_rules = []
        c.apply(s)
        backup = c.save()
        text = self.path.read_text()
        self.assertIn("# favourite", text)
        self.assertIn("# my pwm config", text)
        t = tomllib.loads(text)
        self.assertEqual(t["apps"]["terminal"], "alacritty")
        self.assertEqual(t["bind"][1], {"key": "M-Up", "action": "inc_main", "arg": "2"})
        self.assertNotIn("float_rule", t)
        self.assertEqual(backup.read_text(), SAMPLE)

    def test_keyboard_edit(self):
        c = pwm.Config(self.path)
        s = c.read()
        s.keyboard["options"] = "caps:escape"
        s.keyboard["repeat_delay"] = 300
        del s.keyboard["repeat_rate"]
        c.apply(s)
        c.save()
        text = self.path.read_text()
        self.assertIn("# home", text)
        kb = tomllib.loads(text)["keyboard"]
        self.assertEqual(kb, {"layout": "pt", "options": "caps:escape", "repeat_delay": 300})

    def test_no_keyboard_section_added_on_noop(self):
        self.path.write_text("[theme]\nactive = \"d77\"\n")
        c = pwm.Config(self.path)
        c.apply(c.read())
        c.save()
        self.assertNotIn("keyboard", self.path.read_text())

    def test_backup_only_once(self):
        c = pwm.Config(self.path)
        self.assertIsNotNone(c.save())
        self.assertIsNone(c.save())

    def test_validate(self):
        ok = pwm.Settings(theme="mine", palettes={"mine": {
            "black": "#000000", "white": "#ffffffff", "grey": "0x333333", "accent": "#ff8800"}})
        self.assertEqual(pwm.validate(ok), [])
        bad = pwm.Settings(
            theme="nope",
            window_rules=[("", "10")],
            float_rules=[pwm.FloatRule("x", 1.5)],
            bar_widgets=["clock", "weather"],
            binds=[pwm.Bind("Mod4+x", "spawn"), pwm.Bind("M-a", "inc_main", "x"),
                   pwm.Bind("M-b", "toggle_scratchpad"), pwm.Bind("M-b", "toggle_scratchpad")],
            keyboard={"layout": "pt us", "repeat_rate": 0})
        errs = "\n".join(pwm.validate(bad))
        for needle in ("'nope'", "empty class", "1-9", "between 0 and 1", "'weather'",
                       "penrose format", "needs a command", "whole number",
                       "more than once", "only be bound to one key",
                       "has spaces", "repeat rate must be"):
            self.assertIn(needle, errs)


if __name__ == "__main__":
    unittest.main()
