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
            "frost",
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
        self.use_shell("utumno")
        for verb, command in verbs.items():
            self.log.write_text("")
            self.assertEqual(self.run_verb(verb).returncode, 0)
            self.assertEqual(self.logged("qsd77"), [f"qsd77 -c utumno {command}"])

    def test_quickshell_d77_name_means_utumno(self):
        # quickshell-d77 is archived; a name saved before that targets Utumno.
        self.use_shell("quickshell-d77")
        result = self.run_verb("launcher")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c utumno launcher"])
        self.assertEqual(self.logged("notify-send"), [])

    def test_dashboard_only_where_it_exists(self):
        self.use_shell("utumno")
        self.run_verb("dashboard")
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c utumno dashboard"])

        self.log.write_text("")
        self.use_shell("helium-d77")
        result = self.run_verb("dashboard")
        self.assertEqual(result.returncode, 0)
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

    def test_frost_actions_and_missing_ai(self):
        self.use_shell("frost-d77")
        for verb in ("launcher", "wallpaper", "session", "dashboard", "lock"):
            self.log.write_text("")
            self.assertEqual(self.run_verb(verb).returncode, 0)
            self.assertEqual(self.logged("frost"), [f"frost {verb}"])

        self.log.write_text("")
        self.assertEqual(self.run_verb("ai").returncode, 0)
        self.assertEqual(self.logged("frost"), [])
        self.assertEqual(len(self.logged("notify-send")), 1)

    def test_frost_lock_failure_warns_critically(self):
        self.use_shell("frost-d77")
        self.stub("frost", "exit 1")
        result = self.run_verb("lock")
        self.assertEqual(result.returncode, 1)
        self.assertIn("-u critical", self.logged("notify-send")[0])

    def test_helium_opens_then_closes(self):
        self.use_shell("helium-d77")
        self.run_verb("launcher")
        self.assertEqual(self.logged("helium-launcher"), ["helium-launcher "])

        self.log.write_text("")
        self.stub("pkill", "exit 0")
        self.run_verb("launcher")
        self.assertEqual(self.logged("helium-launcher"), [])
        self.assertEqual(len(self.logged("pkill")), 1)

    def test_helium_lock_prefers_helium_locker(self):
        self.use_shell("helium-d77")
        self.stub("amorphis")
        self.stub("swaylock")
        self.stub("hyprlock")
        self.assertEqual(self.run_verb("lock", path=self.isolated_path()).returncode, 0)
        self.assertEqual(self.logged("helium-locker"), ["helium-locker "])
        self.assertEqual(self.logged("amorphis"), [])
        self.assertEqual(self.logged("swaylock"), [])
        self.assertEqual(self.logged("hyprlock"), [])

    def test_helium_lock_falls_back_in_order(self):
        self.use_shell("helium-d77")
        (self.bin / "helium-locker").unlink()
        self.stub("amorphis")
        self.stub("swaylock")
        self.stub("hyprlock")
        self.assertEqual(self.run_verb("lock", path=self.isolated_path()).returncode, 0)
        self.assertEqual(self.logged("amorphis"), ["amorphis --backend wayland --effect blur"])
        self.assertEqual(self.logged("swaylock"), [])

        self.log.write_text("")
        (self.bin / "amorphis").unlink()
        self.assertEqual(self.run_verb("lock", path=self.isolated_path()).returncode, 0)
        self.assertEqual(self.logged("swaylock"), ["swaylock "])
        self.assertEqual(self.logged("hyprlock"), [])

        self.log.write_text("")
        (self.bin / "swaylock").unlink()
        self.assertEqual(self.run_verb("lock", path=self.isolated_path()).returncode, 0)
        self.assertEqual(self.logged("hyprlock"), ["hyprlock "])

    def test_helium_lock_without_a_locker_warns_critically(self):
        self.use_shell("helium-d77")
        (self.bin / "helium-locker").unlink()
        result = self.run_verb("lock", path=self.isolated_path())
        self.assertEqual(result.returncode, 1)
        self.assertIn("helium-locker, amorphis, swaylock or hyprlock", result.stderr)
        self.assertIn("-u critical", self.logged("notify-send")[0])

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

    def test_frost_daemon_is_detected_but_locker_is_not(self):
        self.stub("pgrep", f'[ "$1 $2" = "-x frost" ] && {{ echo {os.getpid()}; exit 0; }}\nexit 1')
        self.stub("tr", "printf 'frost\\nrun\\n'")
        self.assertEqual(self.run_verb("session").returncode, 0)
        self.assertEqual(self.logged("frost"), ["frost session"])

        self.log.write_text("")
        self.stub("tr", "printf 'frost\\nlock\\n'")
        result = self.run_verb("session")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no active shell", result.stderr)
        self.assertEqual(self.logged("frost"), [])

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

    def session(self, *args, desktop="wasp", path=None):
        env = {
            "PATH": path or f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "XDG_CURRENT_DESKTOP": desktop,
        }
        return subprocess.run(["sh", str(SCRIPT), *args], env=env, capture_output=True,
                              text=True, check=False, stdin=subprocess.DEVNULL)

    def x11(self, *args, desktop="whiplash", path=None):
        """An X11 session, as whiplash-session --backend x11 or wmd77 sets it up."""
        env = {
            "PATH": path or f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "DISPLAY": ":7",
        }
        if desktop is not None:
            env["XDG_CURRENT_DESKTOP"] = desktop
        if desktop == "whiplash":
            env["XDG_SESSION_TYPE"] = "x11"
        return subprocess.run(["sh", str(SCRIPT), *args], env=env, capture_output=True,
                              text=True, check=False, stdin=subprocess.DEVNULL)

    def x11_process(self, display=":7"):
        """A process of the X11 session on `display`, for pgrep to report."""
        proc = subprocess.Popen(["sleep", "60"], env={"DISPLAY": display, "PATH": "/usr/bin:/bin"})
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        return proc.pid

    def test_atg_verbs(self):
        self.use_shell("atg")
        for verb in ("launcher", "wallpaper", "session"):
            self.log.write_text("")
            self.assertEqual(self.x11(verb).returncode, 0)
            self.assertEqual(self.logged("qsd77"), [f"qsd77 -c atg {verb}"])

    def test_atg_locks_with_amorphis_on_x11(self):
        self.stub("amorphis")
        self.use_shell("atg")
        self.assertEqual(self.x11("lock").returncode, 0)
        self.assertEqual(self.logged("amorphis"), ["amorphis --backend x11"])

    def test_atg_lock_never_starts_a_second_locker(self):
        self.stub("amorphis")
        pid = self.x11_process()
        self.stub("pgrep", f'[ "$1 $2" = "-x amorphis" ] && {{ echo {pid}; exit 0; }}\nexit 1')
        self.use_shell("atg")
        self.assertEqual(self.x11("lock").returncode, 0)
        self.assertEqual(self.logged("amorphis"), [])

    def test_atg_has_no_dashboard_or_ai(self):
        self.use_shell("atg")
        for verb in ("dashboard", "ai"):
            self.log.write_text("")
            self.assertEqual(self.x11(verb).returncode, 0)
            self.assertEqual(self.logged("qsd77"), [])
            self.assertEqual(len(self.logged("notify-send")), 1)

    def test_running_atg_is_found_on_x11(self):
        self.stub("pgrep", f"echo {self.x11_process()}; exit 0")
        self.x11("launcher")
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c atg launcher"])

    def test_atg_of_another_display_is_left_alone(self):
        # Another X session on another VT runs its own ATG.
        self.stub("pgrep", f"echo {self.x11_process(':8')}; exit 0")
        result = self.x11("launcher")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no active shell", result.stderr)
        self.assertEqual(self.logged("qsd77"), [])

    def test_wayland_shell_choice_is_ignored_quietly_on_x11(self):
        # One `shell` override for both backends: on X11 a Wayland name just
        # doesn't apply. No warning on every key press.
        self.stub("pgrep", f"echo {self.x11_process()}; exit 0")
        self.use_shell("utumno")
        result = self.x11("launcher")
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c atg launcher"])
        self.assertNotIn("unknown shell", result.stderr)

    def test_atg_is_not_a_wayland_shell(self):
        self.stub("pgrep", "echo 1; exit 0")
        self.use_shell("atg")
        self.run_verb("launcher")
        self.assertNotIn("qsd77 -c atg launcher", self.logged("qsd77"))

    def test_display_without_wayland_counts_as_x11(self):
        # wmd77 from startx: no XDG_SESSION_TYPE, no XDG_CURRENT_DESKTOP.
        self.use_shell("atg")
        self.assertEqual(self.x11("session", desktop=None).returncode, 0)
        self.assertEqual(self.logged("qsd77"), ["qsd77 -c atg session"])

    def test_x11_choice_is_kept_apart(self):
        (self.config / "kantele" / "shell-whiplash").write_text("utumno\n")
        (self.config / "kantele" / "shell-whiplash-x11").write_text("atg\n")
        out = self.x11("status").stdout
        self.assertIn("compositor=whiplash\n", out)
        self.assertIn("session=x11\n", out)
        self.assertIn("chosen=atg\n", out)
        self.assertIn("chosen=utumno\n", self.session("status", desktop="whiplash").stdout)

    def test_wmd77_found_by_its_process_under_startx(self):
        pid = self.x11_process()
        self.stub("pgrep", f'[ "$1 $2" = "-x wmd77" ] && {{ echo {pid}; exit 0; }}\nexit 1')
        (self.config / "kantele" / "shell-wmd77-x11").write_text("atg\n")
        out = self.x11("status", desktop=None).stdout
        self.assertIn("compositor=wmd77\n", out)
        self.assertIn("chosen=atg\n", out)

    def test_x11_without_a_known_window_manager(self):
        self.assertEqual(self.x11("status", desktop=None).returncode, 2)
        # wasp and spitfire are Wayland only.
        self.assertEqual(self.x11("status", desktop="wasp").returncode, 2)

    def test_x11_start_leaves_a_running_atg_alone(self):
        self.stub("pgrep", f"echo {self.x11_process()}; exit 0")
        self.stub("qs")
        (self.config / "kantele" / "shell-whiplash-x11").write_text("atg\n")
        self.assertEqual(self.x11("start").returncode, 0)
        self.assertEqual(self.logged("qs "), [])

    def test_x11_switch_refuses_a_wayland_shell(self):
        result = self.x11("switch", "utumno")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown shell", result.stderr)

    def test_x11_setup_names_the_backend(self):
        self.stub("kantele")
        (self.config / "kantele" / "shell-whiplash-x11").write_text("atg\n")
        (self.config / "kantele" / "shell-whiplash-x11.previous").write_text("none\n")
        self.assertEqual(self.x11("restore").returncode, 0)
        self.assertEqual(self.logged("kantele"),
                         ["kantele shell-setup --wm whiplash --backend x11 --autostart off --bar default"])

    def test_start_without_a_choice_does_nothing(self):
        result = self.session("start")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), "")

    def test_session_commands_need_wasp_or_spitfire(self):
        for command in ("start", "stop", "status", "keep", "restore"):
            self.assertEqual(self.session(command, desktop="sway").returncode, 2)

    def test_status_reports_the_choice(self):
        (self.config / "kantele" / "shell-wasp").write_text("fabric-d77\n")
        (self.config / "kantele" / "shell-wasp.previous").write_text("none\n")
        out = self.session("status").stdout
        self.assertIn("compositor=wasp\n", out)
        self.assertIn("chosen=fabric-d77\n", out)
        self.assertIn("previous=none\n", out)
        self.assertIn("pending=no\n", out)

    def test_each_compositor_has_its_own_choice(self):
        (self.config / "kantele" / "shell-wasp").write_text("fabric-d77\n")
        (self.config / "kantele" / "shell-spitfire").write_text("utumno\n")
        self.assertIn("chosen=utumno\n", self.session("status", desktop="spitfire").stdout)
        self.assertIn("chosen=fabric-d77\n", self.session("status").stdout)

    def test_switch_refuses_an_unknown_shell(self):
        result = self.session("switch", "noctalia")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown shell", result.stderr)

    def test_switch_refuses_a_missing_shell(self):
        result = self.session("switch", "helium-d77", path=self.isolated_path())
        self.assertEqual(result.returncode, 1)
        self.assertIn("not installed", result.stderr)

    def test_switch_refuses_while_locked(self):
        self.stub("fabric-d77")
        self.stub("pgrep", '[ "$2" = amorphis ] && { echo 1; exit 0; }\nexit 1')
        result = self.session("switch", "fabric-d77")
        self.assertEqual(result.returncode, 1)
        self.assertIn("locked", result.stderr)
        self.assertEqual(self.logged("fabric-d77"), [])

    def test_restore_without_a_previous_shell_warns(self):
        result = self.session("restore")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no previous shell", result.stderr)

    def test_restore_to_none_clears_the_choice(self):
        self.stub("kantele")
        (self.config / "kantele" / "shell-wasp").write_text("fabric-d77\n")
        (self.config / "kantele" / "shell-wasp.previous").write_text("none\n")
        self.assertEqual(self.session("restore").returncode, 0)
        self.assertFalse((self.config / "kantele" / "shell-wasp").exists())
        self.assertEqual(self.logged("kantele"),
                         ["kantele shell-setup --wm wasp --autostart off --bar default"])

    def test_keep_clears_only_the_pending_marker(self):
        pending = self.config / "kantele" / "shell-wasp.pending"
        pending.write_text("token\n")
        (self.config / "kantele" / "shell-wasp.previous").write_text("utumno\n")
        self.assertEqual(self.session("keep").returncode, 0)
        self.assertFalse(pending.exists())
        self.assertTrue((self.config / "kantele" / "shell-wasp.previous").exists())

    def test_is_executable_in_the_repo(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
