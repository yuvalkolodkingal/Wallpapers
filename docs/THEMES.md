# Wallpaper themes

Four dark themes pair the collection with readable terminal and shell colors. Each includes the standard Omarchy palette, Hyprland border colors, and its matching Full HD wallpapers.

| Theme | Colors | First background | Wallpapers |
| --- | --- | --- | --- |
| Canopy | Forest, soft lime, butterfly gold | Fig Thief | 7 |
| Lagoon | Deep teal, sage, water lavender | Violet Water | 5 |
| Ember | Warm charcoal, amber, coral | Last Amber | 2 |
| Dusk | Plum, rose, lavender | Rose City | 4 |

## Install on Omarchy

Requires Python 3.11 or newer. Run these commands from the repository root:

```bash
python scripts/theme.py list
python scripts/theme.py install all --dry-run
python scripts/theme.py install all
```

This copies the themes into `~/.config/omarchy/themes/ykg-canopy`, `ykg-lagoon`, `ykg-ember`, and `ykg-dusk`. To install only one, replace `all` with its name. Installation does not change the running desktop. Repeating an identical installation is harmless; a differing existing destination is refused. To update a modified install, rename its directory to a backup first.

The repository stores relative background symlinks; the installer copies the actual images. Installed themes remain usable if this checkout moves or is removed. A Git clone on Linux preserves these links. A ZIP extraction tool that flattens symlinks may require replacing them with their referenced images before installation.

## Activate when ready

```bash
python scripts/theme.py apply canopy --dry-run
python scripts/theme.py apply canopy
```

The `apply` command calls `omarchy theme set ykg-canopy`, then reloads Hyprland and checks for config errors. It runs only inside an active Hyprland session and requires an unchanged installation matching this checkout. Omarchy applies the palette to its shell, supported terminals, and other themed applications using the system's own templates and hooks.

You can also select an installed theme in Omarchy's theme picker or use its own commands:

```bash
omarchy theme current
omarchy theme set ykg-lagoon
omarchy theme bg next
```

Write down your previous theme name before switching if you want to return to it later. Theme installation and activation do not edit your monitor settings, keybindings, gaps, or window rules.

## Compatibility and customization

The supplied `hyprland.lua` follows the installed Hyprland 0.56.2 / Omarchy Lua configuration format: `hl.config` sets the active and inactive borders for windows and groups. It is not a legacy `hyprland.conf` snippet. These files were checked against the installed templates without changing the live desktop. The palettes remain useful on other desktops, but the installer and activation command target Omarchy.

`colors.toml` uses flat named values, including background, foreground, accent, ANSI colors, and their bright counterparts. Omarchy generates its application configs from these values. The supplied Lua repeats the two `hyprland_*_border` values; keep those in sync when changing a palette. Foreground and accent colors were checked against the background for text contrast.

This repository contains several themes, so use its installer instead of `omarchy theme install <repository-url>`, which expects one theme at the repository root.

To inspect the installation in a disposable folder:

```bash
python scripts/theme.py install all --dest /tmp/wallpaper-theme-preview
```

This copies files only. The `--dest` option is not accepted by `apply`, which always addresses your real user-local Omarchy theme directory.

Photos and palettes: Yuval Kolodkin-Gal ([@yuvalkolodkingal](https://github.com/yuvalkolodkingal)).
