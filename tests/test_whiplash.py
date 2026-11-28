"""The whiplash backend: config.toml edited in place, checked by whiplash's rules."""

import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from kantele import shellctl, shellkeys
from kantele.backends import whiplash as wl

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from kantele.ui import luapage
    from kantele.ui import whiplash as whiplash_ui
except ImportError:
    QApplication = None

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


PROFILES = """\
terminal = "alacritty"

# Wayland by default.
autostart = [
    "awww-daemon",
    "dunst",
    "kantele-shell start",
]

[keybinds]
"Super+space" = "spawn qsd77 -c utumno launcher"
"Super+t" = "spawn kantele-shell lock"
"Super+n" = "spawn kantele-shell dashboard"
"Print" = "spawn grim shot.png"

# Xorg session profile.
[x11]
autostart = [
  "dunst",
  "amorphis-idle",
]

[x11.keybinds]
"Super+space" = "spawn qsd77 -c atg launcher"
"Super+a" = false
"Super+t" = "spawn amorphis --backend x11"
"Super+x" = "spawn qsd77 -c atg session"
"Super+y" = "spawn qsd77 -c atg wallpaper"
"XF86AudioMute" = "spawn qsd77 -c atg ipc call osd volumeMuteToggle"
"Print" = 'spawn scrot "$HOME/shot.png"'
"Super+n" = 'spawn env GDK_BACKEND=x11 /usr/share/quickshell/atg/monitor/d77-monitor cpu'
"Super+Shift+z" = false
"""


class WhiplashProfilesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config_home = Path(tmp.name)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.config_home / "whiplash").mkdir()
        self.path = self.config_home / "whiplash" / "config.toml"
        self.path.write_text(PROFILES)

    def test_reads_the_backend_profiles(self):
        s = wl.Config(self.path).read()
        self.assertEqual(s.backend_autostart["x11"], ["dunst", "amorphis-idle"])
        self.assertIsNone(s.backend_autostart["wayland"])
        self.assertIs(s.backend_binds["x11"]["Super+a"], False)
        self.assertIsNone(s.backend_binds["wayland"])
        self.assertEqual(s.autostart_for("wayland"), ["awww-daemon", "dunst", "kantele-shell start"])
        self.assertEqual(s.autostart_for("x11"), ["dunst", "amorphis-idle"])
        self.assertEqual(wl.validate(s), [])

    def test_save_without_changes_keeps_the_file(self):
        config = wl.Config(self.path)
        config.save(config.read())
        self.assertEqual(self.path.read_text(), PROFILES)

    def test_shell_start_goes_where_each_backend_runs_it(self):
        config = wl.Config(self.path)
        s = config.read()
        self.assertTrue(s.shell_autostart_on("wayland"))
        self.assertFalse(s.shell_autostart_on("x11"))
        s.set_shell_autostart(True, "x11")
        config.save(s)
        data = tomllib.loads(self.path.read_text())
        self.assertEqual(data["x11"]["autostart"], ["dunst", "amorphis-idle", "kantele-shell start"])
        self.assertIn("kantele-shell start", data["autostart"])

        s = wl.Config(self.path).read()
        s.set_shell_autostart(False, "wayland")
        wl.Config(self.path).save(s)
        data = tomllib.loads(self.path.read_text())
        self.assertNotIn("kantele-shell start", data["autostart"])
        self.assertIn("kantele-shell start", data["x11"]["autostart"])

    def test_turning_one_backend_off_keeps_a_shared_entry_for_the_other(self):
        self.path.write_text('autostart = ["dunst", "kantele-shell start"]\n')
        s = wl.Config(self.path).read()
        s.set_shell_autostart(False, "x11", other_wants_it=True)
        wl.Config(self.path).save(s)
        data = tomllib.loads(self.path.read_text())
        self.assertEqual(data["autostart"], ["dunst", "kantele-shell start"])
        self.assertEqual(data["x11"]["autostart"], ["dunst"])

    def test_without_profiles_off_still_edits_the_shared_list(self):
        self.path.write_text('autostart = ["dunst", "kantele-shell start"]\n')
        s = wl.Config(self.path).read()
        s.set_shell_autostart(False, "wayland")
        wl.Config(self.path).save(s)
        self.assertEqual(self.path.read_text(), 'autostart = ["dunst"]\n')

    def test_finds_the_atg_commands_kantele_shell_covers(self):
        s = wl.Config(self.path).read()
        found = {combo: new for combo, _old, new in wl.shell_key_overrides(s)}
        self.assertEqual(found, {
            "Super+space": "spawn kantele-shell launcher",
            "Super+t": "spawn kantele-shell lock",
            "Super+x": "spawn kantele-shell session",
            "Super+y": "spawn kantele-shell wallpaper",
        })

    def test_replacing_keeps_the_rest_of_x11_keybinds(self):
        config = wl.Config(self.path)
        s = config.read()
        self.assertEqual(len(wl.replace_shell_key_overrides(s)), 4)
        config.save(s)
        text = self.path.read_text()
        data = tomllib.loads(text)["x11"]["keybinds"]
        self.assertEqual(data["Super+x"], "spawn kantele-shell session")
        self.assertIs(data["Super+a"], False)
        self.assertIs(data["Super+Shift+z"], False)
        self.assertIn("d77-monitor cpu", data["Super+n"])
        self.assertIn("osd volumeMuteToggle", data["XF86AudioMute"])
        self.assertIn('scrot "$HOME/shot.png"', data["Print"])
        self.assertIn("# Xorg session profile.", text)
        self.assertEqual(wl.shell_key_overrides(wl.Config(self.path).read()), [])

    def test_validate_checks_the_profile_keybinds(self):
        s = wl.Config(self.path).read()
        s.backend_binds["x11"]["Super+q"] = "fly away"
        s.backend_binds["x11"]["Hyper+q"] = "close"
        errors = "\n".join(wl.validate(s))
        self.assertIn("[x11.keybinds] 'Super+q': unknown action 'fly'", errors)
        self.assertIn("unknown modifier 'Hyper'", errors)

    def test_setup_turns_the_x11_shell_on_and_off(self):
        shellkeys.setup("whiplash", autostart="on", backend="x11")
        data = tomllib.loads(self.path.read_text())
        self.assertEqual(data["x11"]["autostart"][-1], "kantele-shell start")
        shellkeys.setup("whiplash", autostart="off", backend="x11")
        data = tomllib.loads(self.path.read_text())
        self.assertNotIn("kantele-shell start", data["x11"]["autostart"])
        self.assertIn("kantele-shell start", data["autostart"])

    def test_an_atg_line_counts_as_starting_a_shell_on_x11(self):
        s = wl.Config(self.path).read()
        s.backend_autostart["x11"].append("QT_QPA_PLATFORM=xcb qs -n -d -c atg")
        wl.Config(self.path).save(s)
        self.assertEqual(shellctl.autostart_shells("whiplash", "x11"),
                         ["QT_QPA_PLATFORM=xcb qs -n -d -c atg"])
        self.assertEqual(shellctl.autostart_shells("whiplash"), [])
        shellctl.drop_autostart_shells("whiplash", "x11")
        self.assertEqual(tomllib.loads(self.path.read_text())["x11"]["autostart"],
                         ["dunst", "amorphis-idle"])


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

    def test_drops_the_shell_the_autostart_starts(self):
        self.path.write_text(SAMPLE)
        shellkeys.setup("whiplash", autostart="on")
        self.assertEqual(shellctl.autostart_shells("whiplash"), ["qsd77 run -c utumno"])
        self.assertEqual(shellctl.drop_autostart_shells("whiplash"), ["qsd77 run -c utumno"])
        self.assertEqual(tomllib.loads(self.path.read_text())["autostart"],
                         ["dunst", "kantele-shell start"])
        self.assertEqual(shellctl.autostart_shells("whiplash"), [])
        self.assertFalse(shellctl.config_starts_a_shell(self.path))

    def test_lua_compositors_never_have_their_autostart_edited(self):
        self.assertEqual(shellctl.autostart_shells("wasp"), [])

    @unittest.skipIf(QApplication is None, "needs PyQt6")
    def test_next_login_offers_to_remove_the_other_shell(self):
        app = QApplication.instance() or QApplication([])
        self.path.write_text(SAMPLE)
        with mock.patch.object(wl, "reload_running", return_value="Saved."), \
                mock.patch.object(shellctl, "installed", return_value=True):
            page = whiplash_ui.WhiplashPage(self.path)
            tab = dict(page.parts)["Shell"]
            self.assertIn("config.toml also starts", tab.warning.text())
            tab.combo.setCurrentIndex(tab.combo.findData("utumno"))
            with mock.patch.object(luapage.QMessageBox, "exec",
                                   lambda box: box.defaultButton().click()):
                tab.use_next_login()
        data = tomllib.loads(self.path.read_text())
        self.assertEqual(data["autostart"], ["dunst", "kantele-shell start"])
        self.assertEqual(shellctl.chosen("whiplash"), "utumno")
        self.assertEqual(dict(page.parts)["Shell"].warning.text(), "")
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
