"""The whiplash backend: config.toml edited in place, checked by whiplash's rules."""

import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from kantele import shellctl, shellkeys
from kantele.backends import whiplash as wl

SAMPLE = """\
# my whiplash config
terminal = "alacritty"
mod = "Alt"
gaps = 4

border = { width = 2, focused = "#aa96da", normal = "#3b3b4f" }

autostart = [
  "dunst",
  "qsd77 run -c utumno",  # the bar
]

[keyboard]
layout = "pt"
variant = ""
repeat_rate = 25

[rules."brave-browser"]
workspace = 9

[scratchpads."term"]
command = "alacritty --class scratch-term"
app_id = "scratch-term"

[gestures]
"3-left" = "workspace-prev"

[keybinds]
# launchers
"Mod+Shift+Return" = "terminal"
"Mod+p" = "spawn wmenu-run"
"Super+x" = "spawn qsd77 -c utumno session"
"Mod+s" = "toggle-scratchpad term"
"Mod+1" = "workspace 1"
"""


class WhiplashTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "config.toml"
        self.path.write_text(SAMPLE)

    def roundtrip(self, change):
        c = wl.Config(self.path)
        s = c.read()
        change(s)
        self.assertEqual(wl.validate(s), [])
        c.save(s)
        return self.path.read_text(), tomllib.loads(self.path.read_text())

    def test_reads_every_section(self):
        s = wl.Config(self.path).read()
        self.assertEqual(s.general["gaps"], 4)
        self.assertEqual(s.general["focus_follows_mouse"], False)  # whiplash's default
        self.assertEqual(s.autostart, ["dunst", "qsd77 run -c utumno"])
        self.assertEqual(s.rules, [wl.Rule("brave-browser", 9, None)])
        self.assertEqual(s.scratchpads[0].app_id, "scratch-term")
        self.assertEqual(s.gestures[0].key, "3-left")
        self.assertEqual(s.binds[1], wl.Bind("Mod+p", "spawn", "wmenu-run"))
        self.assertEqual(wl.validate(s), [])

    def test_save_without_changes_keeps_the_file(self):
        text, _ = self.roundtrip(lambda s: None)
        self.assertEqual(text, SAMPLE)

    def test_new_top_level_key_goes_before_the_tables(self):
        text, data = self.roundtrip(lambda s: s.general.update(focus_follows_mouse=True))
        self.assertIs(data["focus_follows_mouse"], True)
        self.assertNotIn("focus_follows_mouse", data["keybinds"])
        self.assertLess(text.index("focus_follows_mouse"), text.index("[keyboard]"))

    def test_edits_keep_comments(self):
        def change(s):
            s.general["gaps"] = 8
            s.border["width"] = 3
            s.binds[1].arg = "fuzzel"
        text, data = self.roundtrip(change)
        self.assertEqual(data["gaps"], 8)
        self.assertEqual(data["border"]["width"], 3)
        self.assertEqual(data["keybinds"]["Mod+p"], "spawn fuzzel")
        self.assertIn("# launchers", text)
        self.assertIn("# my whiplash config", text)

    def test_rules_scratchpads_gestures(self):
        def change(s):
            s.rules = [wl.Rule("firefox", 2, None), wl.Rule("pavucontrol", None, True)]
            s.scratchpads.append(wl.Scratchpad("notes", "foot -e nvim", "", 0.5, None))
            s.gestures.append(wl.Gesture(4, "up", "fullscreen"))
        _, data = self.roundtrip(change)
        self.assertEqual(data["rules"], {"firefox": {"workspace": 2},
                                         "pavucontrol": {"float": True}})
        self.assertEqual(data["scratchpads"]["notes"], {"command": "foot -e nvim", "width": 0.5})
        self.assertEqual(data["gestures"]["4-up"], "fullscreen")

    def test_shell_autostart_edits_the_list_in_place(self):
        text, data = self.roundtrip(lambda s: setattr(s, "shell_autostart", True))
        self.assertEqual(data["autostart"][-1], "kantele-shell start")
        self.assertIn('  "dunst",\n', text)  # still one entry per line
        text, data = self.roundtrip(lambda s: setattr(s, "shell_autostart", False))
        self.assertNotIn("kantele-shell start", data["autostart"])

    def test_no_keybinds_table_stays_absent(self):
        self.path.write_text('gaps = 2\n')
        s = wl.Config(self.path).read()
        self.assertIsNone(s.binds)
        self.assertEqual(len(s.effective_binds()), len(wl.DEFAULT_BINDS))
        _, data = self.roundtrip(lambda s: s.general.update(gaps=6))
        self.assertNotIn("keybinds", data)

    def test_validate_mirrors_whiplash(self):
        s = wl.Config(self.path).read()
        s.general["mod"] = "Hyper"
        s.general["layouts"] = ["tall", "grid"]
        s.border["focused"] = "purple"
        s.touchpad["speed"] = 3
        s.rules.append(wl.Rule("mpv", 12, None))
        s.gestures.append(wl.Gesture(2, "left", "fullscreen"))
        s.binds.append(wl.Bind("Mod+1", "close"))            # same key twice
        s.binds.append(wl.Bind("Mod+q", "toggle-scratchpad", "nope"))
        s.binds.append(wl.Bind("Hyper+q", "close"))
        errs = "\n".join(wl.validate(s))
        for needle in ("Mod key 'Hyper'", "Unknown layout 'grid'", "focused colour",
                       "Touchpad speed", "no workspace 12", "3 to 5 fingers",
                       "'Mod+1' is bound more than once", "no scratchpad 'nope'",
                       "unknown modifier 'Hyper'"):
            self.assertIn(needle, errs)

    def test_combo_helpers(self):
        self.assertEqual(wl.normalize_combo("shift+Mod+J"), "Mod+Shift+j")
        self.assertEqual(wl.combo_from_penrose("M-S-x", "Super"), "Mod+Shift+x")
        self.assertEqual(wl.combo_from_penrose("M-x", "Alt"), "Super+x")

    def test_config_starts_a_shell_reads_toml_comments(self):
        self.assertTrue(shellctl.config_starts_a_shell(self.path))
        self.path.write_text('autostart = ["dunst"]  # was: "qsd77 run -c utumno"\n')
        self.assertFalse(shellctl.config_starts_a_shell(self.path))


class WhiplashShellKeysTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config_home = Path(tmp.name)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.config_home / "whiplash").mkdir()
        self.path = self.config_home / "whiplash" / "config.toml"

    def test_adds_the_verbs_and_keeps_existing_keys(self):
        self.path.write_text(SAMPLE)
        messages = shellkeys.apply("whiplash")
        binds = {b.combo: (b.action, b.arg) for b in wl.Config(self.path).read().binds}
        self.assertEqual(binds["Super+p"], ("spawn", "kantele-shell launcher"))
        self.assertEqual(binds["Super+Shift+z"], ("spawn", "kantele-shell restore"))
        # whiplash keeps every binding in config.toml, so the shell keys
        # replace what the file had there (it was backed up first).
        self.assertEqual(binds["Super+x"], ("spawn", "kantele-shell session"))
        self.assertEqual(binds["Mod+p"], ("spawn", "wmenu-run"))
        self.assertIn("Super+x: replaces 'spawn qsd77 -c utumno session'.", messages)
        backup = self.config_home / "kantele" / "pre-shell" / "whiplash" / "config.toml"
        self.assertEqual(backup.read_text(), SAMPLE)

    def test_without_keybinds_the_built_in_keys_are_kept(self):
        self.path.write_text("gaps = 4\n")
        shellkeys.apply("whiplash")
        binds = wl.Config(self.path).read().binds
        # Super+a/x/y are replaced in place; p, z, n and Shift+z are new.
        self.assertEqual(len(binds), len(wl.DEFAULT_BINDS) + 4)
        self.assertIn(wl.Bind("Super+a", "spawn", "kantele-shell ai"), binds)
        self.assertIn(wl.Bind("Mod+j", "focus-down"), binds)

    def test_setup_toggles_the_autostart_only(self):
        self.path.write_text(SAMPLE)
        shellkeys.setup("whiplash", autostart="on", bar="off")
        data = tomllib.loads(self.path.read_text())
        self.assertEqual(data["autostart"][-1], "kantele-shell start")
        shellkeys.setup("whiplash", autostart="off", bar="default")
        self.assertNotIn("kantele-shell start", tomllib.loads(self.path.read_text())["autostart"])


if __name__ == "__main__":
    unittest.main()
