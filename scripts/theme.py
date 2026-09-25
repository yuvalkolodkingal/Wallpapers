#!/usr/bin/env python3
"""Install wallpapers or Hyprland/Omarchy themes without replacing user files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = Path.home() / '.config/omarchy/themes'
PREFIX = 'ykg-'


def theme_names() -> list[str]:
    return sorted(p.name for p in (ROOT / 'themes').iterdir()
                  if p.is_dir() and (p / 'colors.toml').is_file())


def files_for(name: str, target: str = 'omarchy') -> dict[Path, Path]:
    """Return validated data and Lua from this theme, resolving local photos."""
    directory = ROOT / 'themes' / name
    palette = tomllib.loads((directory / 'colors.toml').read_text())
    for key in ('background', 'foreground', 'accent', 'muted'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', palette.get(key, '')):
            raise ValueError(f'{name}: invalid or missing palette key {key}')
    files = {Path(p): directory / p for p in ('colors.toml', 'hyprland.lua')}
    if target == 'hyprland':
        files[Path('hyprland.conf')] = directory / 'hyprland.conf'
    backgrounds = sorted((directory / 'backgrounds').iterdir())
    if not backgrounds:
        raise ValueError(f'{name}: no backgrounds')
    for photo in backgrounds:
        resolved = photo.resolve(strict=True)
        if not resolved.is_relative_to(ROOT / 'wallpapers') or not resolved.is_file():
            raise ValueError(f'{name}: background must resolve to a repository wallpaper: {photo.name}')
        files[Path('backgrounds') / photo.name] = resolved
    for source in files.values():
        if not source.is_file():
            raise ValueError(f'Missing theme file: {source}')
    return files


def digest(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def identical(target: Path, files: dict[Path, Path]) -> bool:
    if target.is_symlink() or not target.is_dir():
        return False
    # Extra local files or symlinks count as a modified install; never discard them.
    existing = {p.relative_to(target) for p in target.rglob('*') if not p.is_dir() or p.is_symlink()}
    if existing != set(files):
        return False
    return all(not (target / rel).is_symlink() and digest(target / rel) == digest(source)
               for rel, source in files.items())


def default_destination(target: str) -> Path:
    if target == 'omarchy':
        # Omarchy's own commands use this fixed location.
        return DEFAULT_DEST
    if target == 'hyprland':
        return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'hypr/themes'
    if sys.platform == 'darwin':
        return Path.home() / 'Pictures/Yuval Wallpapers'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'yuval-wallpapers'


def install(names: list[str], destination: Path, dry_run: bool, target_kind: str = 'omarchy') -> None:
    destination = destination.expanduser().absolute()
    plans = []
    # Preflight every target before writing anything.
    for name in names:
        files = files_for(name, target_kind)
        target = destination / (PREFIX + name)
        if target.exists() or target.is_symlink():
            if identical(target, files):
                print(f'Already installed: {target}')
                continue
            raise ValueError(f'Refusing to replace existing path: {target}\n'
                             'Rename that path to a backup before installing again.')
        plans.append((name, files, target))
    for name, files, target in plans:
        count = sum(p.parts[0] == 'backgrounds' for p in files)
        print(f'{"Would install" if dry_run else "Installing"}: {name} -> {target} ({count} backgrounds)')
        if dry_run:
            continue
        destination.mkdir(parents=True, exist_ok=True)
        # Copy photos, not symlinks: installed themes survive a moved/deleted checkout.
        with tempfile.TemporaryDirectory(prefix='.ykg-stage-', dir=destination) as scratch:
            stage = Path(scratch) / (PREFIX + name)
            stage.mkdir()
            for relative, source in files.items():
                output = stage / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, output)
            # Reserve the destination exclusively; never overwrite an existing path.
            target.mkdir()
            try:
                for entry in stage.iterdir():
                    shutil.move(str(entry), str(target / entry.name))
            except BaseException:
                print(f'Installation interrupted; partial new directory retained at {target}', file=sys.stderr)
                raise
    if plans and not dry_run:
        print('Installed. Your active desktop theme has not changed.')
    if target_kind == 'hyprland':
        print('Load one installed hyprland.lua (current Lua configs) or hyprland.conf (legacy configs).')
        print('See https://github.com/yuvalkolodkingal/Wallpapers/blob/main/docs/INSTALL.md#plain-hyprland')


def install_wallpapers(names: list[str], destination: Path, dry_run: bool, resolution: str) -> None:
    """Merge selected photos, preflighting every collision before copying anything."""
    destination = destination.expanduser().absolute()
    manifest = json.loads((ROOT / 'metadata/collection.json').read_text())
    key = 'master' if resolution == 'master' else 'fullhd'
    files = {Path('COPYRIGHT'): ROOT / 'COPYRIGHT'}
    for photo in manifest['wallpapers']:
        if photo['theme'] not in names:
            continue
        source = (ROOT / photo[key]).resolve(strict=True)
        if not source.is_relative_to(ROOT / 'wallpapers') or not source.is_file():
            raise ValueError(f'Invalid wallpaper path: {photo[key]}')
        files[Path(resolution) / source.name] = source
    plans = []
    for relative, source in files.items():
        target = destination / relative
        for parent in [destination, *target.parents]:
            if parent == destination.parent:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ValueError(f'Expected a normal destination directory: {parent}')
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink: {target}')
        if target.exists():
            if not target.is_file() or digest(target) != digest(source):
                raise ValueError(f'Refusing to replace differing file: {target}')
        else:
            plans.append((source, target))
    print(f'{"Would install" if dry_run else "Installing"}: {len(files)-1} wallpapers ({resolution}) -> {destination}')
    if dry_run:
        return
    for source, target in plans:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create also protects files created after the preflight.
        with source.open('rb') as source_file, target.open('xb') as output:
            shutil.copyfileobj(source_file, output)
    print('Wallpapers installed. Choose an image in your desktop wallpaper settings.')


def apply(name: str, dry_run: bool) -> None:
    target = DEFAULT_DEST / (PREFIX + name)
    if not identical(target, files_for(name)):
        raise ValueError(f'Theme is missing or differs from the repository. Run: python scripts/theme.py install {name}')
    command = ['omarchy', 'theme', 'set', PREFIX + name]
    print(('Would run: ' if dry_run else 'Running: ') + ' '.join(command), flush=True)
    if dry_run:
        return
    if not shutil.which('omarchy'):
        raise ValueError('Omarchy is not installed or is not on PATH.')
    if not shutil.which('hyprctl') or not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        raise ValueError('Run apply inside your active Hyprland session.')
    subprocess.run(command, check=True)
    subprocess.run(['hyprctl', 'reload'], check=True)
    result = subprocess.run(['hyprctl', 'configerrors'], check=True, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout, end='')
        raise ValueError('Hyprland reported config errors; inspect the output above.')
    print('Theme applied; Hyprland reports no config errors.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list', help='List palettes and wallpaper counts')
    install_parser = sub.add_parser('install', help='Copy wallpapers or themes; never activates them')
    install_parser.add_argument('theme', choices=theme_names() + ['all'])
    install_parser.add_argument('--target', choices=['omarchy', 'hyprland', 'wallpapers'], default='omarchy')
    install_parser.add_argument('--dest', type=Path, help='Override the destination directory')
    install_parser.add_argument('--resolution', choices=['1920x1080', 'master'], default='1920x1080',
                                help='Wallpaper-only export size; theme backgrounds use 1920x1080')
    install_parser.add_argument('--dry-run', action='store_true')
    apply_parser = sub.add_parser('apply', help='Explicitly switch the running desktop to one installed theme')
    apply_parser.add_argument('theme', choices=theme_names())
    apply_parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'list':
            for name in theme_names():
                files = files_for(name)
                palette = tomllib.loads((ROOT / 'themes' / name / 'colors.toml').read_text())
                print(f'{name:8s}  {len(files)-2} backgrounds  accent {palette["accent"]}  installs as {PREFIX}{name}')
        elif args.command == 'install':
            names = theme_names() if args.theme == 'all' else [args.theme]
            destination = args.dest or default_destination(args.target)
            if args.target == 'wallpapers':
                install_wallpapers(names, destination, args.dry_run, args.resolution)
            elif args.resolution != '1920x1080':
                raise ValueError('--resolution master is only available with --target wallpapers')
            else:
                install(names, destination, args.dry_run, args.target)
        else:
            apply(args.theme, args.dry_run)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
