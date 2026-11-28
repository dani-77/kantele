# Plan: ATG as the X11 shell (wmd77 and Whiplash's X11 session)

## Status

> **Rule for whoever works on this plan (person or agent):** read this section
> first and update it at the end of every step. Mark each step where it is,
> with the legend below. Only mark `[x]` what was actually verified; `[~]` means
> done but waiting for a test. Real-session tests only become `[x]` once Daniel
> confirms them.
>
> Legend: `[ ]` to do · `[~]` done, to test · `[x]` done

- **Current step:** done. Released 2026-11-28: Kantele 0.6.0 and whiplash 0.4.1 (Void glibc and musl, AUR, d77-iso), and the d77void wmd77 variant starts the shell with `kantele-shell start` (main, for the next ISO).
- **Last update:** 2026-11-28.

## Goal

The same promise as the Wayland shells, on X11: open Kantele, pick the shell,
keep the same keys. On X11 there is one shell for now, ATG. It is offered on:

- **wmd77**, which today starts ATG from its `startup.sh`;
- **Whiplash's X11 session** (Whiplash 0.4.0), whose `whiplash-session` starts
  ATG by itself.

Whiplash is the hard case: one `config.toml` drives two backends. The shared
`autostart` and `[keybinds]` are written for Wayland, `[x11]` / `[wayland]` can
replace the autostart per backend, and `[x11.keybinds]` / `[wayland.keybinds]`
override single bindings.

## Where things stand (2026-11-28)

- `kantele-shell` only knows Wayland. `on_this_display` compares
  `WAYLAND_DISPLAY`, `compositor_or_usage` accepts wasp, spitfire and whiplash,
  and the shells are Utumno, fabric-d77, helium-d77 and Frost.
- Kantele's Whiplash backend reads and writes the top-level `autostart` only.
  tomlkit keeps `[x11]` / `[wayland]` intact on save, but Kantele doesn't know
  which list runs where. `shell_autostart` adds `kantele-shell start` to the
  shared list. That is harmless today only because Daniel's `[x11].autostart`
  replaces the shared list on X11. Without an `[x11]` table, the X11 session
  would run `kantele-shell start`, which would try to start a Wayland shell.
- Daniel's `~/.config/whiplash/config.toml` is the reference. The shared
  autostart is Wayland (awww, set-wallpaper, `kantele-shell start`), and
  `[x11].autostart` has the services without any shell. `[x11.keybinds]`
  repeats each shell key with a direct ATG command (`qsd77 -c atg launcher`,
  `amorphis --backend x11`, `d77-monitor cpu`, ATG's OSD for volume and
  brightness) because `kantele-shell <verb>` doesn't reach ATG.
- wmd77 uses Kantele's pwm page with `Flavor` WMD77. Its `[bar]` already has
  `enable` and `reserve_top`, so ATG needs `enable = false` and
  `reserve_top = 48`. wmd77 runs `startup.sh` once per session (since 9f6cf87);
  a restart (`M-S-r`) no longer runs it again.
- `whiplash-session --backend x11` exports `XDG_SESSION_TYPE=x11`, unsets
  `WAYLAND_DISPLAY` and adds `-s 'QT_QPA_PLATFORM=xcb qs -n -d -c atg'` when ATG
  is installed.
- ATG answers `launcher`, `session` and `wallpaper` (each with `toggle`, which
  qsd77 calls) and `osd` over IPC.
  Its system monitor is `monitor/d77-monitor <cpu|memory>`. It has no locker of
  its own, and its session menu uses Amorphis.

## Design

### 1. `kantele-shell` learns X11

The central piece: with it, the **same** `kantele-shell <verb>` bindings work
on both backends, and most of `[x11.keybinds]` stops being needed.

- **Session type:** X11 when `XDG_SESSION_TYPE=x11`, or when `WAYLAND_DISPLAY`
  is unset and `DISPLAY` is set. `on_this_display` compares `DISPLAY` on X11,
  so a shell from another session on another VT is never touched.
- **Compositor:** `whiplash`, from `XDG_CURRENT_DESKTOP` as today, plus `wmd77`.
  wmd77 started by `startx` leaves `XDG_CURRENT_DESKTOP` empty, so it is found
  by a `wmd77` process on the same `DISPLAY`. A display manager sets it to
  `wmd77` through `DesktopNames`.
- **Choices per backend:** `shell-<wm>` stays the Wayland choice, and X11 gets
  `shell-<wm>-x11` (`shell-whiplash-x11`, `shell-wmd77-x11`). The previous and
  pending files follow the same names. Keeping the files apart means switching
  one backend never touches the other.
- **ATG as a shell:**

  | Piece | ATG |
  |---|---|
  | running | `qs_pids atg` (the same pattern as Utumno) |
  | launch | `QT_QPA_PLATFORM=xcb XDG_CONFIG_DIRS=/usr/share:… setsid qs -n -d -c atg` |
  | installed | `/usr/share/quickshell/atg` and `qs` |
  | launcher / session / wallpaper | `qsd77 -c atg <verb>` |
  | lock | `amorphis --backend x11`, never twice |
  | dashboard | no equivalent yet (warns); the System Monitor keeps its own binding |
  | ai | no equivalent (warns) |

- **`start` on X11** starts the X11 choice. If ATG is already running, because
  `whiplash-session` or wmd77's `startup.sh` started it, `start` does nothing,
  as it does today for Wayland shells.
- **The Wayland shells are never started on X11**, and ATG never on Wayland.
  `KNOWN_SHELLS` gains a backend for each name.

### 2. Kantele's Whiplash backend reads the backend profiles

- **Read and write the per-backend tables:** `[x11].autostart`,
  `[wayland].autostart`, `[x11.keybinds]` and `[wayland.keybinds]`. A key set to
  `false` is a valid value that removes a binding on that backend.
- **Effective lists:** "what runs on Wayland" is `[wayland].autostart` if it
  exists, otherwise the shared list. "What runs on X11" is built the same way
  with `[x11]`. The GUI shows them under these names, not as raw tables.
- **`shell_autostart` per backend:** `kantele-shell start` goes into each
  effective list that needs it. With `kantele-shell` aware of X11 (design 1),
  the entry is safe in a list that runs on both, but Kantele still writes it
  where it applies, so the file reads correctly.
- **Shell-starting entries** (`autostart_shells` / `drop_autostart_shells`) are
  searched per list, and the X11 search also recognises ATG launches
  (`qs … -c atg`, `qsd77 run -c atg`).
- **Redundant `[x11.keybinds]`:** with design 1, a key whose shared binding is
  `kantele-shell <verb>` and whose X11 override is the same action written for
  ATG (for example `"Super+space" = "spawn qsd77 -c atg launcher"`) can be
  dropped. Kantele lists these and offers to remove them, and never removes
  them silently. Overrides with no `kantele-shell` verb behind them, such as
  ATG's OSD on the volume and brightness keys, `scrot` or `dmenu_run`, stay.
- **Validation** mirrors Whiplash's own: the same key and action checks in the
  backend tables, plus `false`.

### 3. The GUI

- **Whiplash, Shell tab:** two sections. **Wayland** is today's tab (Utumno,
  fabric-d77, helium-d77, Frost). **X11** offers ATG or nothing, with the same
  Apply / keep / go back flow when Kantele runs inside the X11 session, and
  only the choice otherwise.
- **wmd77, new Shell tab:** "wmd77's bar" or "ATG". Choosing ATG writes
  `[bar] enable = false` and `reserve_top = 48`, then `kantele-shell switch atg`.
  wmd77 needs a restart for the bar change, which is safe now because a restart
  no longer re-runs `startup.sh`. Going back restores the bar and reserve the
  file had before.
- **Warnings, as for `config.lua`:** if wmd77's `startup.sh` starts ATG itself,
  Kantele says so and doesn't edit the script.

### 4. Outside Kantele (proposals, to decide)

- **Whiplash:** `whiplash-session` starts ATG unconditionally, so Kantele could
  never turn ATG off on Whiplash's X11 session. One option: drop the hard-coded
  `-s` and put `kantele-shell start` (or the ATG line, without Kantele) in the
  example config's `[x11].autostart`.
- **d77void:** in the wmd77 variant, replace the `qs … -c atg` line in
  `common/wmd77/startup.sh` with `kantele-shell start`, and ship
  `~/.config/kantele/shell-wmd77-x11` set to `atg` in the skel. Kantele then
  owns the shell from the first login.

## Decisions (Daniel, 2026-11-28)

1. **ATG on Whiplash's X11 session can be turned on and off.** The launch
   moves out of `whiplash-session` into the config's `[x11].autostart`, where
   Kantele adds or removes it.
2. **wmd77 does both.** Its `startup.sh` runs `kantele-shell start` when Kantele
   is installed, and starts ATG directly when it isn't. The d77void skel ships
   the X11 choice set to `atg`.
3. **Redundant `[x11.keybinds]` are replaced.** Kantele offers to rewrite them
   as the `kantele-shell <verb>` they duplicate, and shows the list first.
4. **`dashboard`:** ATG has none yet, so the verb warns that there is no
   equivalent. The System Monitor binding (`Super+n`, `d77-monitor cpu`) stays
   as it is and is not replaced.
5. **`lock` on X11 is Amorphis** (`amorphis --backend x11`), as in ATG's
   session menu.

## Phases

1. [x] `kantele-shell`: X11 detection, wmd77, per-backend choice files, ATG
   (launch, health, verbs). Tests in `tests/test_kantele_shell.py` with a fake
   X11 environment.
2. [x] `shellctl`: each shell's backend, ATG's install packages (Void:
   `quickshell qsd77 atg`; ATG isn't in the AUR yet), per-backend
   `chosen`/`choose`.
3. [x] Whiplash backend: `[x11]`/`[wayland]` tables, effective lists, per-list
   shell detection, the redundant-override report. Tests against a copy of
   Daniel's config.
4. [x] GUI: Whiplash Shell tab with Wayland and X11 sections; wmd77 Shell tab.
5. [x] Decided proposals outside Kantele (Whiplash, d77void):
   - whiplash branch `atg-from-config` (7938d3a): `whiplash-session` no longer
     adds ATG; the d77 X11 default and the example's `[x11]` list start it.
     Checked in Xvfb (no config, example, own list without ATG) and Kantele
     swaps the example's ATG line for `kantele-shell start`.
   - d77void branch `wmd77-kantele-shell`: `startup.sh` runs
     `kantele-shell start` when Kantele is installed, ATG directly otherwise;
     the skel picks ATG. Only for an ISO built after this Kantele is released.
6. [x] Release and packaging (Void, AUR, d77-iso where Kantele is).

Tests follow the existing notes:
- isolate `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME`;
- use Xvfb rather than Xephyr for key tests;
- never restart a shell in the session Daniel is using.
