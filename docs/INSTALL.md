# Install wallpapers and themes

All photography is by **Yuval Kolodkin-Gal**. These installers copy the collection
into your user account. They preserve identical files and stop if an existing
file differs. No administrator access is needed.

## Linux, macOS, and other Unix systems

Requires Bash, curl, tar, and Python 3.11 or newer. Run:

```sh
curl -fsSL https://raw.githubusercontent.com/yuvalkolodkingal/Wallpapers/main/install.sh | bash
```

The installer detects Omarchy or Hyprland on Linux. On other desktops and macOS,
it installs wallpapers. It does not switch the desktop automatically.

| System / target | Default destination | Included |
| --- | --- | --- |
| Omarchy | `~/.config/omarchy/themes/ykg-*` | Four complete Omarchy themes with matching backgrounds |
| Plain Hyprland | `${XDG_CONFIG_HOME:-~/.config}/hypr/themes/ykg-*` | Lua and legacy Hyprlang border configs, palettes, backgrounds |
| Other Linux / Unix | `${XDG_DATA_HOME:-~/.local/share}/yuval-wallpapers` | Wallpaper files and copyright credit |
| macOS | `~/Pictures/Yuval Wallpapers` | Wallpaper files and copyright credit |

Choose one theme, or download the full-resolution wallpaper masters:

```sh
curl -fsSL https://raw.githubusercontent.com/yuvalkolodkingal/Wallpapers/main/install.sh | bash -s -- --theme dusk
curl -fsSL https://raw.githubusercontent.com/yuvalkolodkingal/Wallpapers/main/install.sh | bash -s -- --target wallpapers --resolution master
```

Other options:

- `--theme all|canopy|lagoon|ember|dusk` (default: `all`).
- `--target auto|omarchy|hyprland|wallpapers` (default: `auto`).
- `--dest "/custom/path"` overrides the destination.
- `--dry-run` downloads and checks the payload without writing to the destination.
- `--resolution 1920x1080|master` applies to wallpaper-only installs.
- `--help` shows usage without downloading.

To install and activate **Canopy on Omarchy** in one command:

```sh
curl -fsSL https://raw.githubusercontent.com/yuvalkolodkingal/Wallpapers/main/install.sh | bash -s -- --theme canopy --apply
```

`--apply` requires one theme, the default installation path, and an active
Hyprland session with Omarchy. It reloads Hyprland and checks configuration errors.
Use [the Omarchy theme guide](THEMES.md) for switching among installed themes.

## Windows

Open **PowerShell** and run:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/yuvalkolodkingal/Wallpapers/main/install.ps1')))
```

This uses Windows PowerShell 5.1+ or PowerShell 7; Python and Git are not needed.
The default location is your Windows Pictures folder, under `Yuval Wallpapers`.
It contains `1920x1080` images, copyright credit, and installation notes.

To select one set, full-resolution masters, and a different destination:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/yuvalkolodkingal/Wallpapers/main/install.ps1'))) -Theme dusk -Resolution master -Destination 'D:\Wallpapers'
```

Add `-DryRun` to preview installation, or `-Help` for usage. Choose an installed
photo through your desktop's wallpaper settings. Hyprland's window-manager themes
apply on Linux; Windows and macOS receive the photographs.

If you prefer to download and inspect either installer first, save the script
from the URL above, then run the local file. No execution-policy changes are
made by the Windows installer.

## Plain Hyprland

The installer places the themes in your Hyprland configuration directory. It
leaves the main config and wallpaper-manager choice to you. Add one matching
include after your existing appearance settings.

For current Lua configs, in `hyprland.lua`:

```lua
dofile((os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config"))
  .. "/hypr/themes/ykg-canopy/hyprland.lua")
```

For legacy Hyprlang configs, in `hyprland.conf`:

```ini
source = ~/.config/hypr/themes/ykg-canopy/hyprland.conf
```

Replace `canopy` with another installed theme. Adjust the path if you used
`--dest` or a custom `XDG_CONFIG_HOME`. The two formats are alternatives; use the
one supported by your Hyprland version. These snippets change window and group
border colors. Omarchy additionally generates its app colors from `colors.toml`.

After saving your config:

```sh
hyprctl reload
hyprctl configerrors
```

Select a photo from that theme's `backgrounds/` folder with your existing
wallpaper manager. Current [Hyprland color documentation](https://wiki.hypr.land/Configuring/Basics/Variables/)
and [legacy 0.54 documentation](https://wiki.hypr.land/0.54.0/Configuring/Variables/)
describe the supported border properties.

## Download behavior and validation

Both installers download a complete repository snapshot over HTTPS before
installing. The payload is pinned to the commit recorded as `SOURCE_REF` in
`install.sh` and `$SourceRef` in `install.ps1`, so a run does not mix versions.
Temporary downloads are removed when the installer exits. Neither installer
removes existing themes or changes desktop settings by default.

The Bash installer validates archive paths and symlinks before extraction.
PowerShell extracts only the selected regular image and metadata files. Existing
file conflicts are checked before any destination files are copied.

Maintainer checks:

```sh
bash -n install.sh
python3 -m unittest discover -s tests -v
uv run scripts/verify_collection.py
```

The Windows script targets PowerShell 5.1-compatible syntax. Its parser and
installation behavior are exercised with PowerShell 7 on Linux using disposable
folders; native Windows and macOS desktop integration has not been tested here.
