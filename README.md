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
| [wasp](https://github.com/dani-77/wasp) | `~/.config/wasp/config.lua` | planned |
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

## Usage

```
kantele                 # configure the running WM
kantele --wm pwm        # pick one explicitly
kantele --config FILE   # edit another file (e.g. for testing)
```

## Install

Needs Python 3.11+, PyQt6 and tomlkit (Void: `python3-pyqt6`
`python3-pyqt6-gui` `python3-pyqt6-widgets` `python3-tomlkit`).

```
make test
sudo make install        # PREFIX=/usr by default
```

## License

MIT
