"""`kantele shell-keys` and `kantele-shell reset`, on real Lua and a scratch config."""

import contextlib
import io
import os
import pathlib
import pty
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from kantele import shellkeys
from kantele.backends import spitfire, wasp

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "kantele-shell"

WASP_CONFIG = """\
wasp = {}
wasp.modkey = "alt"
wasp.keys = {}
local keys = wasp.keys
keys[#keys + 1] = { mods = { "mod" }, key = "space", action = "setlayout" }
keys[#keys + 1] = { mods = { "super" }, key = "a", action = "spawn", cmd = { "mine" } }
"""
SPITFIRE_CONFIG = """\
spitfire.bind("Mod4", "t", function() spitfire.layout.set("tile") end)
spitfire.bind("Mod4", "a", function() spitfire.spawn("mine") end)
"""
EXPECTED_VERBS = {"launcher", "lock", "dashboard", "session", "wallpaper", "ai", "restore"}


@unittest.skipUnless(shutil.which(wasp.LUA), "needs lua5.4")
class ShellKeysTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.config_home = self.root / "config"
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for module, text in ((wasp, WASP_CONFIG), (spitfire, SPITFIRE_CONFIG)):
            directory = self.config_home / module.NAME
            directory.mkdir(parents=True)
            (directory / "config.lua").write_text(text)
            reload_patch = mock.patch.object(module, "reload_running", return_value="Saved.")
            reload_patch.start()
            self.addCleanup(reload_patch.stop)

    def live(self, wm, name):
        return self.config_home / wm / name

    def binds(self, wm):
        return shellkeys.BACKENDS[wm][0].Config().read().binds

    def reset(self, *args):
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        for name in ("pgrep", "pkill", "spitfirectl", "notify-send"):
            stub = bin_dir / name
            stub.write_text(f'#!/bin/sh\necho "{name} $*" >>"{self.root}/log"\nexit 1\n')
            stub.chmod(0o755)
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.config_home),
        }
        return subprocess.run(
            ["setsid", "sh", str(SCRIPT), "reset", *args],
            env=env, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
        )

    def test_every_verb_is_bound_on_both(self):
        for wm in shellkeys.BACKENDS:
            shellkeys.apply(wm)
            commands = {b.arg for b in self.binds(wm)}
            self.assertEqual(commands, {f"kantele-shell {v}" for v in EXPECTED_VERBS})
            self.assertTrue(all(b.action == "spawn" for b in self.binds(wm)))

    def test_wasp_keys_use_super_and_win_over_config_lua(self):
        messages = shellkeys.apply("wasp")
        effective = wasp._run_lua(self.live("wasp", "config.lua"), skip=False)
        first = effective["keys"][0]
        self.assertEqual(first["mods"], ["super"])
        self.assertEqual(first["cmd"], ["kantele-shell", "launcher"])
        self.assertIn("super+a: replaces the binding from config.lua.", messages)

    def test_spitfire_unbinds_the_key_in_config_lua(self):
        shellkeys.apply("spitfire")
        dump = spitfire._run_lua(self.live("spitfire", "config.lua"), skip=False)
        combos = [(b["mods"], b["key"]) for b in dump["binds"]]
        self.assertEqual(combos.count(("Mod4", "a")), 1)
        kept = [b for b in dump["binds"] if b["mods"] == "Mod4" and b["key"] == "t"]
        self.assertEqual(len(kept), 1)

    def test_applying_twice_changes_nothing(self):
        shellkeys.apply("wasp")
        before = self.live("wasp", "kantele.lua").read_text()
        messages = shellkeys.apply("wasp")
        self.assertEqual(self.live("wasp", "kantele.lua").read_text(), before)
        self.assertIn("Nothing to add.", messages)

    def test_a_key_you_bound_in_kantele_is_kept(self):
        config = wasp.Config()
        settings = config.read()
        settings.binds = [wasp.Bind("super+p", "spawn", "my-launcher")]
        config.save(settings)
        messages = shellkeys.apply("wasp")
        commands = {b.combo: b.arg for b in self.binds("wasp")}
        self.assertEqual(commands["super+p"], "my-launcher")
        self.assertIn("super+p: kept your own Kantele binding, not launcher.", messages)

    def test_backup_is_taken_once_before_any_change(self):
        original = self.live("wasp", "config.lua").read_text()
        shellkeys.apply("wasp")
        backup = self.config_home / "kantele/pre-shell/wasp"
        self.assertEqual((backup / "config.lua").read_text(), original)
        self.assertFalse((backup / "kantele.lua").exists())

        config = wasp.Config()
        settings = config.read()
        settings.values[("gaps", "inner")] = 42
        config.save(settings)
        shellkeys.apply("wasp")
        self.assertEqual((backup / "config.lua").read_text(), original)
        self.assertFalse((backup / "kantele.lua").exists())

    def test_reset_restores_and_removes_what_was_not_there(self):
        original = self.live("wasp", "config.lua").read_text()
        shellkeys.apply("wasp")
        self.assertIn("kantele.lua", self.live("wasp", "config.lua").read_text())
        result = self.reset("wasp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.live("wasp", "config.lua").read_text(), original)
        self.assertFalse(self.live("wasp", "kantele.lua").exists())
        self.assertFalse((self.config_home / "kantele/pre-shell/wasp").exists())

    def test_reset_restores_an_earlier_kantele_lua(self):
        config = spitfire.Config()
        settings = config.read()
        settings.values[("gaps", "inner")] = 42
        config.save(settings)
        earlier = self.live("spitfire", "kantele.lua").read_text()
        shellkeys.apply("spitfire")
        self.assertEqual(self.reset("spitfire").returncode, 0)
        self.assertEqual(self.live("spitfire", "kantele.lua").read_text(), earlier)

    def test_reset_without_a_terminal_refuses_changed_files(self):
        shellkeys.apply("wasp")
        edited = self.live("wasp", "config.lua").read_text() + "-- my edit\n"
        self.live("wasp", "config.lua").write_text(edited)
        result = self.reset("wasp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cancelled", result.stderr)
        self.assertEqual(self.live("wasp", "config.lua").read_text(), edited)
        self.assertTrue((self.config_home / "kantele/pre-shell/wasp").exists())

    def reset_answering(self, answer):
        """Runs reset on a real terminal, answering its question."""
        bin_dir = self.root / "bin"
        pid, fd = pty.fork()
        if pid == 0:
            os.execve("/bin/sh", ["sh", str(SCRIPT), "reset", "wasp"], {
                "PATH": f"{bin_dir}:/usr/bin:/bin",
                "HOME": str(self.root),
                "XDG_CONFIG_HOME": str(self.config_home),
            })
        output = b""
        answered = False
        while True:
            try:
                data = os.read(fd, 1024)
            except OSError:
                break
            if not data:
                break
            output += data
            if not answered and b"[y/N]" in output:
                os.write(fd, answer + b"\n")
                answered = True
        os.close(fd)
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status), answered

    def test_reset_on_a_terminal_asks_about_changed_files(self):
        shellkeys.apply("wasp")
        self.reset("wasp-stubs-only")  # creates the stubs
        original = (self.config_home / "kantele/pre-shell/wasp/config.lua").read_text()
        edited = self.live("wasp", "config.lua").read_text() + "-- my edit\n"
        self.live("wasp", "config.lua").write_text(edited)

        code, asked = self.reset_answering(b"n")
        self.assertTrue(asked)
        self.assertEqual(code, 1)
        self.assertEqual(self.live("wasp", "config.lua").read_text(), edited)

        code, asked = self.reset_answering(b"y")
        self.assertTrue(asked)
        self.assertEqual(code, 0)
        self.assertEqual(self.live("wasp", "config.lua").read_text(), original)

    def test_restore_key_has_shift_on_both(self):
        for wm, combo in (("wasp", "super+shift+z"), ("spitfire", "Mod4+Shift+z")):
            shellkeys.apply(wm)
            commands = {b.combo: b.arg for b in self.binds(wm)}
            self.assertEqual(commands[combo], "kantele-shell restore")

    def test_wasp_autostart_is_added_to_config_lua_entries(self):
        self.live("wasp", "config.lua").write_text(
            WASP_CONFIG + 'wasp.autostart = { { "dunst" } }\n')
        shellkeys.setup("wasp", autostart="on")
        effective = wasp._run_lua(self.live("wasp", "config.lua"), skip=False)
        self.assertEqual(effective["autostart"], [["dunst"], ["kantele-shell", "start"]])

        shellkeys.setup("wasp", autostart="off")
        effective = wasp._run_lua(self.live("wasp", "config.lua"), skip=False)
        self.assertEqual(effective["autostart"], [["dunst"]])

    def test_wasp_autostart_without_a_list_in_config_lua(self):
        shellkeys.setup("wasp", autostart="on")
        effective = wasp._run_lua(self.live("wasp", "config.lua"), skip=False)
        self.assertEqual(effective["autostart"], [["kantele-shell", "start"]])

    def test_spitfire_autostart_is_in_the_generated_file(self):
        shellkeys.setup("spitfire", autostart="on")
        self.assertTrue(spitfire.Config().read().shell_autostart)
        self.assertIn('spitfire.autostart({ "kantele-shell start" })',
                      self.live("spitfire", "kantele.lua").read_text())

    def test_autostart_survives_later_saves(self):
        for wm in shellkeys.BACKENDS:
            backend = shellkeys.BACKENDS[wm][0]
            shellkeys.setup(wm, autostart="on")
            config = backend.Config()
            config.save(config.read())
            self.assertTrue(backend.Config().read().shell_autostart)

    def test_bar_on_off_and_back_to_config_lua(self):
        self.live("wasp", "config.lua").write_text(
            WASP_CONFIG + "wasp.bar = { enable = true }\n")
        path = ("bar", "enable")
        shellkeys.setup("wasp", bar="off")
        self.assertIs(wasp.Config().read().values[path], False)
        shellkeys.setup("wasp", bar="default")
        self.assertIs(wasp.Config().read().values[path], True)
        self.assertNotIn("bar", wasp.render_overrides(wasp.Config().read()).split("local keys")[0])

    def test_setup_keeps_the_keys(self):
        shellkeys.apply("spitfire")
        before = {b.combo for b in self.binds("spitfire")}
        shellkeys.setup("spitfire", autostart="on", bar="off")
        self.assertEqual({b.combo for b in self.binds("spitfire")}, before)

    def test_reset_without_a_backup_warns(self):
        result = self.reset("wasp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no backup", result.stderr)

    def test_reset_rejects_an_unknown_compositor(self):
        self.assertEqual(self.reset("sway").returncode, 2)

    def test_main_reports_a_broken_config(self):
        self.live("wasp", "config.lua").write_text("this is not lua (\n")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(shellkeys.main(["--wm", "wasp"]), 1)
        self.assertIn("kantele shell-keys:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
