# Shell keys

The same keys do the same thing in wasp and spitfire, with any of the d77 shells.
Each key runs `kantele-shell <verb>`, which translates the verb for the shell that
is running. The compositors' own keys, such as layouts and window focus, are not
part of this: wasp keeps `Alt` as its mod key and spitfire keeps `Super`.

| Key | Action | Verb | quickshell-d77 | Utumno | fabric-d77 | helium-d77 |
|---|---|---|---|---|---|---|
| `Super+P` | Launcher | `launcher` | Yes | Yes | Yes | Yes |
| `Super+Z` | Lock | `lock` | Yes | Yes | Yes | Yes (Amorphis, swaylock or hyprlock) |
| `Super+X` | Session menu | `session` | Yes | Yes | Yes | Yes |
| `Super+Y` | Wallpaper | `wallpaper` | Yes | Yes | Yes | Yes |
| `Super+A` | Ollama chat | `ai` | Yes | Yes | Yes | Yes |
| `Super+N` | Dashboard | `dashboard` | Yes | No | Yes | No |
| `Super+Shift+Z` | Back to the previous shell | `restore` | Yes | Yes | Yes | Yes |

Where a shell has no equivalent, the key shows a notification and does nothing else.

Volume keys stay on `amixer`, as they already are in both compositors' default
`config.lua`. Brightness keys get no binding, since a laptop's firmware usually
handles them. All four shells notice either change and show their on-screen
display, within about two seconds.

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
(`quickshell-d77`, `utumno`, `fabric-d77` or `helium-d77`) in
`~/.config/kantele/shell`.
