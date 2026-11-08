# How the shells came to Kantele

This is how four desktop shells ended up working on two Wayland compositors, and
how Kantele learned to switch between them. It's here as a starting point if you
want to take this further: add a shell or a compositor, or do something bolder
with it. It covers the reasoning and the mistakes, which the code doesn't show.

The projects involved:

| Kind | Projects |
|---|---|
| Compositors | [wasp](https://github.com/dani-77/wasp) (dwl/wlroots), [spitfire](https://github.com/dani-77/spitfire) (Smithay) |
| Shells | [quickshell-d77](https://github.com/dani-77/quickshell-d77) and [Utumno](https://github.com/dani-77/utumno) (Quickshell), [fabric-d77](https://github.com/dani-77/fabric-d77) (Python, GTK), [helium-d77](https://github.com/dani-77/helium-d77) (Rust, Slint) |
| Support | [qsd77](https://github.com/dani-77/qsd77), [Amorphis](https://github.com/dani-77/amorphis), Kantele |

## The goal

Open Kantele, pick a shell, keep working, with the same keys as yesterday. If the
shell fails to come up, you get the old one back without doing anything.

## The order, and why it mattered

The first idea was to start with Kantele. Doing the shells first turned out to be
the decision everything else rested on. A switcher built first would have offered
shells that had no workspaces on these compositors, a bar too short for the screen,
and a lock screen that could lock you out. Those problems were found and fixed where
they belonged, and Kantele was left with only the job of choosing and switching.

1. **Workspaces in every shell**, with Utumno, which already worked, as the reference.
2. **Common keys and a small translator script**, `kantele-shell`.
3. **Close wasp**, then **close spitfire**: every shell through the same checklist
   of autostart, bar, keys, lock, reload and logout, one compositor at a time.
4. **Kantele**: choosing, switching, going back, installing.
5. **Packaging and publishing.**

## How it works

**Workspaces.** Both compositors expose `ext-workspace-v1`, so each shell needs one
client for it, as a fallback after its compositor-specific code:

- quickshell-d77 and Utumno use `Quickshell.WindowManager`.
- fabric-d77 has a small Wayland client in plain Python. The protocol passes no file
  descriptors, so the standard library is enough.
- helium-d77 uses `wayland-client` on its own thread, and `xdg-output` for the bar's width.

**Verbs.** Keybindings call `kantele-shell <verb>` (`launcher`, `lock`, `session`,
`wallpaper`, `dashboard`, `ai`), and the script translates the verb for the shell
that is running. It's plain `sh` because it runs on every key press. The keys are in
[shell-keys.md](shell-keys.md).

**Never editing `config.lua`.** These configs are Lua code, so Kantele owns a
generated `kantele.lua`, loaded from one line at the end of `config.lua`. That also
covers autostart: wasp's list can be appended to, and `spitfire.autostart` adds to
its list on each call, so the user's own entries stay.

**Switching.** `kantele-shell switch` stops the current shell, starts the new one and
checks that it stays healthy for a few seconds in a row. If it doesn't, the old one
comes back straight away. If it does, a separate process waits 15 seconds and goes
back unless told to keep the new one, so this still works if the shell and Kantele
both die. At login, a shell that won't start falls back to the previous one, and
then to the compositor's built-in bar.

## Decisions worth knowing about

- **No common mod key.** wasp keeps `Alt`, spitfire keeps `Super`, and each keeps its
  own keys for layouts and focus. Only the shell's keys are shared. An early draft
  tried to harmonize everything, which meant changing the compositors for no gain.
- **Design defaults against a clean install.** Key collisions were checked against
  each compositor's `examples/config.lua`, not against anyone's personal config. Doing
  the opposite produced a proposal that solved problems a new install doesn't have.
- **Nothing is imposed.** A compositor keeps the shell it came with, or none, until
  you choose one in Kantele.
- **Kantele warns about `config.lua`, and doesn't fix it.** If it already starts a
  shell, that shell wins, and Kantele doesn't edit the file. The warning had to be
  made louder after this caught the project's own author in testing.
- **quickshell stays out of the Void templates' `depends`**, so that it never holds
  back a system upgrade. Installing from Kantele adds it explicitly.

## Traps we fell into

- **`helium-locker` can lock you out.** An upstream `layer-shika` bug makes the
  compositor cancel the lock, and it has also been seen to lock with no way to
  unlock. helium-d77 now locks with Amorphis, then `swaylock`, then `hyprlock`.
  Testing a locker needs a way back in: another VT, or a nested compositor.
- **`loginctl lock-session` is not a fallback.** With nothing listening, it does
  nothing and reports success.
- **`qsd77` exits 0 when an IPC call fails.** Read its output instead. Otherwise a
  failed lock looks like a working one.
- **Process names keep 15 characters.** `pgrep -x helium-wallpaper` never matches.
- **`pkill -f` matches its own caller.** A pattern can hit the shell running the
  command, or anything with that text on its command line, including a test script.
- **Act only on your own display.** The same user can have sessions open on other
  VTs. `kantele-shell` checks `WAYLAND_DISPLAY` in each process's environment. A
  fabric-d77 logout path that ran `pkill -KILL -u $USER` was replaced for this reason.
- **Which binary is running?** Shells installed as packages run from `/usr/share` or
  `/usr/bin`, not from your checkout. A bar that looked broken was an old
  `helium-shell` found on `PATH`, run from inside `target/release` without `./`.
- **One workspace group per monitor.** wasp's model repeated every workspace on a
  second monitor until the widget showed only its own monitor's group.
- **Simulated clicks prove nothing here.** `wlrctl pointer click` failed on a shell
  known to work. Clicks were tested by hand.
- **Packages can look broken right after upload.** SourceForge can serve an HTML page
  or a cut-off file for a while. Compare sizes on the server before believing it.

## Testing without breaking your session

Run a compositor nested inside your session, with its own `XDG_CONFIG_HOME`,
`XDG_STATE_HOME` and `XDG_CACHE_HOME`, so your real autostart doesn't run:

- `WLR_X11_OUTPUTS=2 wasp` or `WLR_WL_OUTPUTS=2 wasp` gives two outputs on one monitor.
- `spitfire --winit` runs nested, but has no virtual pointer, and simulated keys don't
  reach its bindings. `grim` also came out upside down in that mode.
- Lock, logout and starting at login still need a real session.

## Adding a shell

1. Make its workspaces work over `ext-workspace-v1`.
2. Give it a way to be told what to do from outside: IPC, signals or binaries.
3. In `kantele-shell`, add it to `KNOWN_SHELLS`, teach `running_shell` to detect it and
   `all_shell_pids` to list its processes, add `launch_shell` and `shell_healthy`, and
   map each verb. A verb it doesn't have should warn, not fail.
4. In `kantele/shellctl.py`, add it to `SHELLS`, `installed` and the package lists.
5. Run it through the checklist: autostart, bar, keys, lock, reload, logout.

## Adding a compositor

It needs `ext-workspace-v1`, layer-shell and session-lock, a way to reload its config,
and a way to add to its autostart without replacing the list.

1. Add a backend under `kantele/backends/`, on the lines of `wasp.py` and `spitfire.py`.
2. Add it to `BACKENDS` in `kantele/shellkeys.py`, after checking the keys against its
   clean config.
3. Add it to the checks in `kantele-shell` (`compositor_or_usage`, `reset_keys`,
   `reload_compositor`), and run every shell through the checklist on it.

## What's left, and ideas

Not verified yet:

- Nothing has been used in a real Arch session. Packages only went through an install
  test in a clean container, and Install with `paru` or `yay` hasn't been tried.
- `loginctl` for logout was tested on Void with elogind, not on an Arch system without
  systemd.
- quickshell-d77 wasn't re-tested on niri after the widget's rename and per-monitor filter.
- Urgent workspaces haven't been seen in a real case.

Known limits:

- helium-d77 shows the first monitor's workspaces on every monitor, since `helium_wsl`
  has no per-monitor `set` yet. quickshell-d77 and Utumno have one bar, on one monitor.
- `kantele-shell` can only tell a session is locked from external lockers and
  `LockedHint`, not from a shell's own lock screen.
- `helium-backdrop` only knows about wallpapers set through `helium-wallpaper`. From the
  code, it would cover one set any other way.

Ideas:

- **sway support** in Kantele. sway's config isn't Lua either, but it has `include`, so
  Kantele can own a file of its own, included by one line in `config`, the same way it
  owns `kantele.lua` on wasp and spitfire. Check first how sway handles a key bound twice.
- **`kantele-shell` on X11** for the lock and the launcher (pwm, wmd77), with the same
  keys as on Wayland. The four shells are Wayland-only, so the verbs would point
  elsewhere: `amorphis --backend x11`, and `d77run` or `rofi`. No `session` verb: both
  window managers have their own exit menu, built on `dmenu`.
- **Keyboard layout and touchpad for pwm and wmd77.** On X11 the layout comes from the
  X server (`/etc/X11/xorg.conf.d/`), and neither window manager reads one from its
  `config.toml`, so Kantele has nothing to show. The idea: optional `[keyboard]` and
  `[touchpad]` sections, applied at startup and on reload with `setxkbmap` and `xinput`.
  Left empty, the window manager doesn't touch either. Their default `startup.sh` uses
  `synclient`, which only works with the synaptics driver, so check the driver first.
  On hold while other projects depend on pwm as it is.
- A bar on every monitor for the shells that have one.

Ruled out:

- **niri in Kantele.** The four shells already run on niri, and its config supports
  `include optional=true`, so Kantele could own a file there too. But niri refuses a
  config with a key bound twice, across included files too, and falls back to its
  stock behavior, dropping every change the user made. One wrong guess about which keys
  are taken would cost the whole config, and the shells don't need Kantele to run there.
