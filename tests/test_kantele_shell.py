"""kantele-shell's verb translation, run against stub commands."""

import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "kantele-shell"


class KanteleShellTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "log"
        self.log.touch()
        self.config = self.root / "config"
        (self.config / "kantele").mkdir(parents=True)
        # Nothing is running and nothing can be closed, unless a test says so.
        for name in ("pgrep", "pkill"):
            self.stub(name, "exit 1")
        for name in (
            "qsd77",
            "fabric-d77-signal",
            "notify-send",
            "helium-launcher",
            "helium-wallpaper",
            "helium-session",
            "helium-ollama",
            "helium-locker",
        ):
            self.stub(name)

    def stub(self, name, body="exit 0"):
        path = self.bin / name
        path.write_text(f'#!/bin/sh\necho "{name} $*" >>"{self.log}"\n{body}\n')
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def use_shell(self, name):
        (self.config / "kantele" / "shell").write_text(name + "\n")

    def isolated_path(self):
        """A PATH without this machine's own lockers."""
        tools = self.root / "tools"
        tools.mkdir(exist_ok=True)
        for name in ("sh", "head", "dirname", "readlink", "tr"):
            link = tools / name
            if not link.exists():
                link.symlink_to(shutil.which(name))
        return f"{self.bin}:{tools}"

    def run_verb(self, *args, path=None):
        env = {
            "PATH": path or f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.config),
        }
        return subprocess.run(
            ["sh", str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def logged(self, prefix):
        lines = self.log.read_text().splitlines()
        return [line for line in lines if line.startswith(prefix)]

    def test_qsd77_shells_always_pass_their_name(self):
        verbs = {
            "launcher": "launcher",
            "wallpaper": "wallpaper",
            "lock": "locker",
            "session": "session",
            "ai": "ollama",
        }
        for shell in ("quickshell-d77", "utumno"):
            self.use_shell(shell)
            for verb, command in verbs.items():
                self.log.write_text("")
                self.assertEqual(self.run_verb(verb).returncode, 0)
                self.assertEqual(self.logged("qsd77"), [f"qsd77 -c {shell} {command}"])

    def test_dashboard_only_where_it_exists(self):
        self.use_shell("quickshell-d77")
        self.run_verb("dashboard")
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c quickshell-d77 dashboard"])

        for shell in ("utumno", "helium-d77"):
            self.log.write_text("")
            self.use_shell(shell)
            result = self.run_verb("dashboard")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(self.logged("qsd77"), [])
            self.assertEqual(self.logged("helium-"), [])
            self.assertEqual(len(self.logged("notify-send")), 1)

    def test_fabric_signals(self):
        self.use_shell("fabric-d77")
        signals = {
            "launcher": "USR1",
            "session": "USR2",
            "wallpaper": "RTMIN+6",
            "dashboard": "RTMIN+7",
            "lock": "RTMIN+8",
            "ai": "RTMIN+9",
        }
        for verb, signal in signals.items():
            self.log.write_text("")
            self.assertEqual(self.run_verb(verb).returncode, 0)
            self.assertEqual(self.logged("fabric-d77-signal"), [f"fabric-d77-signal {signal}"])

    def test_helium_opens_then_closes(self):
        self.use_shell("helium-d77")
        self.run_verb("launcher")
        self.assertEqual(self.logged("helium-launcher"), ["helium-launcher "])

        self.log.write_text("")
        self.stub("pkill", "exit 0")
        self.run_verb("launcher")
        self.assertEqual(self.logged("helium-launcher"), [])
        self.assertEqual(len(self.logged("pkill")), 1)

    def test_helium_lock_prefers_hyprlock_and_skips_helium_locker(self):
        self.use_shell("helium-d77")
        self.stub("hyprlock")
        self.stub("swaylock")
        self.assertEqual(self.run_verb("lock").returncode, 0)
        self.assertEqual(self.logged("hyprlock"), ["hyprlock "])
        self.assertEqual(self.logged("swaylock"), [])
        self.assertEqual(self.logged("helium-locker"), [])

    def test_helium_lock_falls_back_to_swaylock(self):
        self.use_shell("helium-d77")
        self.stub("swaylock")
        self.assertEqual(self.run_verb("lock", path=self.isolated_path()).returncode, 0)
        self.assertEqual(self.logged("swaylock"), ["swaylock "])
        self.assertEqual(self.logged("helium-locker"), [])

    def test_helium_lock_without_a_locker_warns_critically(self):
        self.use_shell("helium-d77")
        result = self.run_verb("lock", path=self.isolated_path())
        self.assertEqual(result.returncode, 1)
        self.assertIn("hyprlock or swaylock", result.stderr)
        self.assertIn("-u critical", self.logged("notify-send")[0])
        self.assertEqual(self.logged("helium-locker"), [])

    def test_helium_lock_never_toggles(self):
        self.use_shell("helium-d77")
        self.stub("swaylock")
        self.stub("pkill", "exit 0")
        self.stub("pgrep", "exit 0")
        self.assertEqual(self.run_verb("lock", path=self.isolated_path()).returncode, 0)
        self.assertEqual(self.logged("pkill"), [])
        self.assertEqual(self.logged("swaylock"), [])

    def test_lock_without_shell_warns_critically(self):
        result = self.run_verb("lock")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no active shell", result.stderr)
        notifications = self.logged("notify-send")
        self.assertEqual(len(notifications), 1)
        self.assertIn("-u critical", notifications[0])

    def test_qsd77_error_output_counts_as_failure(self):
        self.use_shell("utumno")
        self.stub("qsd77", 'echo "Error: exit status 255"')
        result = self.run_verb("lock")
        self.assertEqual(result.returncode, 1)
        self.assertIn("-u critical", self.logged("notify-send")[0])

    def test_fabric_failure_warns(self):
        self.use_shell("fabric-d77")
        self.stub("fabric-d77-signal", "exit 1")
        result = self.run_verb("lock")
        self.assertEqual(result.returncode, 1)
        self.assertIn("-u critical", self.logged("notify-send")[0])

    def test_running_shell_is_detected(self):
        # Answers only the query for this one process name.
        self.stub("pgrep", '[ "$1 $2" = "-x helium-shell" ] && { echo 1; exit 0; }\nexit 1')
        self.run_verb("session")
        self.assertEqual(self.logged("helium-session"), ["helium-session "])

    def test_config_file_beats_the_running_shell(self):
        self.stub("pgrep", "echo 1; exit 0")
        self.use_shell("utumno")
        self.run_verb("session")
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c utumno session"])

    def test_unknown_shell_in_file_is_ignored(self):
        self.use_shell("noctalia")
        result = self.run_verb("session")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown shell", result.stderr)
        self.assertEqual(self.logged("qsd77"), [])

    def test_bad_usage(self):
        self.assertEqual(self.run_verb().returncode, 2)
        self.assertEqual(self.run_verb("nope").returncode, 2)
        self.assertEqual(self.run_verb("lock", "extra").returncode, 2)

    def test_is_executable_in_the_repo(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
