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
| [spitfire](https://github.com/dani-77/spitfire) | `~/.config/spitfire/config.lua` | planned |

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
order) and **Keybindings** (your overrides, with a key recorder, next to
pwm's built-in keymap).

**Save and apply** asks the running pwm to reload by sending it `SIGHUP`,
which pwm 0.6.5 and newer handle as an in-place restart (your windows stay
open). Older pwm releases don't handle `SIGHUP`, and its default action would
end the session, so Kantele checks first and, on those, asks you to press
Super+Shift+R instead.

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
**Effects** (animations, blur) and **Keybindings** (yours, with a key
recorder, next to `config.lua`'s, which you can override or disable).

**Save and apply** sends `SIGHUP` to wasp, which reloads `config.lua` the same
way mod+shift+r does (wasp 0.10.1 and newer). On older releases Kantele
doesn't send it and asks you to press mod+shift+r.

## Usage

```
kantele                 # configure the running WM
kantele --wm wasp       # pick one explicitly
kantele --config FILE   # edit another file (e.g. for testing)
```

## Install

Needs Python 3.11+, PyQt6, tomlkit and, for wasp, Lua 5.4 (Void:
`python3-pyqt6` `python3-pyqt6-gui` `python3-pyqt6-widgets` `python3-tomlkit`
`lua54`).

```
make test
sudo make install        # PREFIX=/usr by default
```

## License

MIT
