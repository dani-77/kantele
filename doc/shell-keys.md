# Shell keys

The same keys do the same thing in wasp, spitfire and whiplash, with any of the d77
shells.
Each key runs `kantele-shell <verb>`, which translates the verb for the shell that
is running. The compositors' own keys, such as layouts and window focus, are not
part of this: wasp keeps `Alt` as its mod key and spitfire keeps `Super`.

| Key | Action | Verb | Utumno | fabric-d77 | helium-d77 | Frost |
|---|---|---|---|---|---|---|
| `Super+P` | Launcher | `launcher` | Yes | Yes | Yes | Yes |
| `Super+Z` | Lock | `lock` | Yes | Yes | Yes (Amorphis, swaylock or hyprlock) | Yes |
| `Super+X` | Session menu | `session` | Yes | Yes | Yes | Yes |
| `Super+Y` | Wallpaper | `wallpaper` | Yes | Yes | Yes | Yes |
| `Super+A` | Ollama chat | `ai` | Yes | Yes | Yes | No |
| `Super+N` | Dashboard | `dashboard` | Yes | Yes | No | Yes |
| `Super+Shift+Z` | Back to the previous shell | `restore` | Yes | Yes | Yes | Yes |

Where a shell has no equivalent, the key shows a notification and does nothing else.

quickshell-d77 is archived: Utumno superseded it and now carries everything it had,
so Kantele no longer offers, installs or starts it. A `quickshell-d77` saved in
Kantele's files from before counts as Utumno, and a copy still running from an older
session still gets the keys, and is closed when switching shells.

Volume keys stay on `amixer`, as they already are in both compositors' default
`config.lua`. Brightness keys get no binding, since a laptop's firmware usually
handles them. The shells notice either change and show their on-screen
display, within about two seconds. Frost uses its own volume and brightness
commands when invoked directly; these common compositor bindings still use
`amixer`.

## Adding the keys

```
kantele shell-keys                # for the running compositor
kantele shell-keys --wm spitfire  # for a specific one
```

The keys go to `kantele.lua` as ordinary Kantele bindings, so you can change or
disable them on the Keybindings page. A key you already bound in Kantele is left
alone. A key that `config.lua` also binds is overridden, and the command says so.

## Going back

The first run copies `config.lua` and `kantele.lua` to
`~/.config/kantele/pre-shell/<compositor>/`. To put them back and reload the
compositor:

```
kantele-shell reset            # for the running compositor
kantele-shell reset spitfire   # for a specific one
```

If those files changed after the keys were added, including through Kantele's
own pages, `reset` asks first, and without a terminal to ask on it refuses.

## Choosing the shell

The active shell is the one found running. To force one, put its name
(`utumno`, `fabric-d77`, `helium-d77` or `frost-d77`) in
`~/.config/kantele/shell`.
