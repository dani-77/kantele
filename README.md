<p align="center"><img src="assets/kantele.png" alt="Kantele logo" width="256"></p>

<h1 align="center">Kantele</h1>

<p align="center"><i>Tune your window manager, string by string.</i></p>

Kantele is a settings GUI for the d77 window managers. It is named after
"My Kantele", the Amorphis classic from *Elegy*: the kantele is the Finnish
string instrument you tune one string at a time, which is what this tool does
to a window manager — theme, applications, rules, bar and keybindings, one
setting at a time.

## Supported window managers

| WM | Config | Status |
|---|---|---|
| [pwm](https://github.com/dani-77/pwm) | `~/.config/pwm/config.toml` | supported |
| [wasp](https://github.com/dani-77/wasp) | `~/.config/wasp/config.lua` | supported |
| [spitfire](https://github.com/dani-77/spitfire) | `~/.config/spitfire/config.lua` | supported |
| [wmd77](https://github.com/d77void/wmd77) | `~/.config/wmd77/config.toml` | supported (wmd77 0.5.0+) |
| [whiplash](https://github.com/dani-77/whiplash) | `~/.config/whiplash/config.toml` | supported (whiplash 0.2.0+) |

### pwm

Every pwm setting is optional and overlays pwm's built-in defaults, so Kantele
only writes what you change; an empty field means "use pwm's default". The
file is edited in place with [tomlkit](https://github.com/python-poetry/tomlkit):
your comments and layout are kept, and saving without changes leaves the file
byte-for-byte identical. The first time Kantele writes an existing config it
keeps a copy next to it as `config.toml.kantele-bak`.

Pages: **Theme** (active theme, your own palettes with a live bar preview),
**Applications**, **Workspaces** (window class → workspace rules),
**Floating** (classes that float, and their size), **Bar** (widgets and their
order), **Keyboard** (XKB layout, variant, model and options, and key repeat
delay and rate - the same settings as wasp and spitfire; needs pwm 0.6.9 /
wmd77 0.5.2, older releases ignore them) and **Keybindings** (your
overrides, with a key recorder, next to pwm's built-in keymap).

**Save and apply** asks the running pwm to reload by sending it `SIGHUP`,
which pwm 0.6.5 and newer handle as an in-place restart (your windows stay
open). Older pwm releases don't handle `SIGHUP`, and its default action would
end the session, so Kantele checks first and, on those, asks you to press
Super+Shift+R instead.

### wmd77

wmd77 0.5.0 reads the same `config.toml` format as pwm, so it gets the same
pages and the same in-place editing. Only **Bar** differs: wmd77 keeps its
own dwm-style bar, and the page turns it on or off, sets its height, font
size and position, and how much room to keep free at the top for an external
bar such as polybar. Save and apply sends `SIGHUP`, like pwm.

### wasp

wasp's config is Lua code, so Kantele never rewrites it. Your changes go to a
generated file next to it, `kantele.lua`, and `config.lua` gets one line at
its end that loads it (Kantele adds that line on the first save and keeps the
original as `config.lua.kantele-bak`). `kantele.lua` only holds what you
changed: settings are laid over `config.lua`'s values, and your keybindings
are put in front of `config.lua`'s, so they win for the same key. The action
`none` switches a `config.lua` binding off and lets the key through to the
window. Delete `kantele.lua` to drop every Kantele setting.

To show the current values Kantele runs `config.lua` with the system Lua
(`lua5.4`). Bold settings differ from `config.lua`; the ↺ button next to
each one goes back to `config.lua`'s value. Before writing, Kantele loads the
result through Lua and keeps the previous `kantele.lua` if that fails.

Pages: **Windows** (borders, gaps, snap, background), **Bar**, **Keyboard**
(mod key, layout, repeat), **Applications** (terminal, launcher),
**Effects** (animations, blur), **Keybindings** (yours, with a key recorder,
next to `config.lua`'s, which you can override or disable) and **Shell**.

**Save and apply** sends `SIGHUP` to wasp, which reloads `config.lua` the same
way mod+shift+r does (wasp 0.10.1 and newer). On older releases Kantele
doesn't send it and asks you to press mod+shift+r.

### spitfire

Same approach as wasp: your changes go to `~/.config/spitfire/kantele.lua`,
loaded from the last line of `config.lua`, which is otherwise left alone.

spitfire's keybindings are Lua functions, so Kantele lists `config.lua`'s by
the line that defines them rather than by action. Each Kantele binding first
calls `spitfire.unbind` to drop `config.lua`'s binding for that key, then
binds its own; `none` only unbinds, so the key reaches the window.
`spitfire.unbind` is new in spitfire 0.5.5: with older releases
`config.lua`'s binding still wins for keys it already binds.

To read the current values Kantele runs `config.lua` with `lua5.4` and a
stand-in `spitfire` table that records settings and bindings without doing
anything.

Pages: **Windows** (borders, gaps, snap, focus follows mouse, output scale),
**Bar**, **Keyboard**, **Effects** (animation, blur), **Keybindings** and **Shell**.
**Save and apply** runs `spitfirectl reload`.

### whiplash

whiplash's config is TOML, like pwm's, so Kantele edits `config.toml` in place
the same way: comments and layout stay, a save without changes leaves the file
identical, and the first write keeps `config.toml.kantele-bak`. There is no
side file: TOML can't include one.

whiplash reloads `config.toml` by itself whenever it is written, so **Save**
and **Save and apply** do the same. Before writing, Kantele checks everything
with whiplash's own rules (keys, actions, colours, workspaces, touchpad
ranges, rules, scratchpads, gestures), so a save never ends in whiplash's
error notification.

The **Keybindings** page shows the whole keymap: a `[keybinds]` table replaces
whiplash's built-in keys, so the file always lists every active binding.
Without that table the page shows the built-in keys, and the first change
writes them all, never one key alone.

Pages: **Windows** (terminal, mod key, gaps, workspaces, layouts, focus
follows mouse, borders), **Keyboard**, **Touchpad**, **Rules** (app id →
workspace, floating), **Scratchpads**, **Gestures**, **Monitors** (scale and
position), **Keybindings** and **Shell**.

## Desktop shells

On wasp, spitfire and whiplash, the **Shell** tab picks which d77 shell runs:
[Utumno](https://github.com/dani-77/utumno),
[quickshell-d77](https://github.com/dani-77/quickshell-d77) (archived — Utumno superseded it),
[fabric-d77](https://github.com/dani-77/fabric-d77),
[helium-d77](https://github.com/dani-77/helium-d77) or
[Frost](https://github.com/dani-77/frost). Each compositor keeps its own
choice. With nothing chosen, it keeps whatever it came with. A shell that isn't
installed can be installed from the tab: with `pkexec xbps-install` on Void, which
needs a polkit agent running and the d77 repository, and with `paru` or `yay` in a
terminal on Arch.

**Apply now** stops the current shell, starts the new one and turns the built-in
bar off. If you don't confirm within 15 seconds, or the new shell doesn't come up,
the previous one comes back. **Use from next login** only saves the choice, which
also works for a compositor you aren't running. If `config.lua` starts a shell by
itself, the tab warns you: remove that entry, as Kantele doesn't edit the file. On
whiplash the autostart list is in `config.toml`, which Kantele already edits, so
choosing a shell there offers to take the other shell's entry out for you.

`kantele shell-keys` gives both compositors the same keys for shell actions, and
`kantele-shell reset` undoes it. See [doc/shell-keys.md](doc/shell-keys.md). For how
this came together, and how to add a shell or compositor, see
[doc/shells-plan.md](doc/shells-plan.md).

From a terminal, `kantele-shell` has `status`, `switch <shell>`, `keep`, `restore`,
`start` and `stop`. `Super+Shift+Z` also goes back to the previous shell.

## Usage

```
kantele                 # configure the running WM (says so if it isn't supported)
kantele --wm wmd77      # pick one explicitly
kantele --config FILE   # edit another file (e.g. for testing)
kantele shell-keys      # add the common shell keys (wasp, spitfire)
```

## Install

Needs Python 3.11+, PyQt6, tomlkit and, for wasp and spitfire, Lua 5.4 (Void:
`python3-pyqt6` `python3-pyqt6-gui` `python3-pyqt6-widgets` `python3-tomlkit`
`lua54`).

```
make test
sudo make install        # PREFIX=/usr by default
```

## License

MIT
