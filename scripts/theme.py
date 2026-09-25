#!/usr/bin/env python3
"""Install the collection's Omarchy themes without replacing existing files."""
from __future__ import annotations

import argparse
import hashlib
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


def files_for(name: str) -> dict[Path, Path]:
    """Return validated data and Lua from this theme, resolving local photos."""
    directory = ROOT / 'themes' / name
    palette = tomllib.loads((directory / 'colors.toml').read_text())
    for key in ('background', 'foreground', 'accent', 'muted'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', palette.get(key, '')):
            raise ValueError(f'{name}: invalid or missing palette key {key}')
    files = {Path(p): directory / p for p in ('colors.toml', 'hyprland.lua')}
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


def install(names: list[str], destination: Path, dry_run: bool) -> None:
    destination = destination.expanduser().absolute()
    plans = []
    # Preflight every target before writing anything.
    for name in names:
        files = files_for(name)
        target = destination / (PREFIX + name)
        if target.exists() or target.is_symlink():
            if identical(target, files):
                print(f'Already installed: {target}')
                continue
            raise ValueError(f'Refusing to replace existing path: {target}\n'
                             'Rename that path to a backup before installing again.')
        plans.append((name, files, target))
    for name, files, target in plans:
        print(f'{"Would install" if dry_run else "Installing"}: {name} -> {target} ({len(files)-2} backgrounds)')
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
    install_parser = sub.add_parser('install', help='Copy themes into user-local Omarchy; never activates them')
    install_parser.add_argument('theme', choices=theme_names() + ['all'])
    install_parser.add_argument('--dest', type=Path, default=DEFAULT_DEST,
                                help='Theme parent directory (default: ~/.config/omarchy/themes)')
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
            install(theme_names() if args.theme == 'all' else [args.theme], args.dest, args.dry_run)
        else:
            apply(args.theme, args.dry_run)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
