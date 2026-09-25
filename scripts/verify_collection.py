#!/usr/bin/env python3
"""Check published photos, attribution, recipes and themes without the originals."""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageCms

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = 'Yuval Kolodkin-Gal'
HEX = re.compile(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z')
ALLOWED_INFO = {'jfif', 'jfif_version', 'jfif_unit', 'jfif_density',
                'dpi', 'exif', 'icc_profile'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def repo_path(value):
    path = Path(value)
    require(not path.is_absolute(), f'Absolute path in metadata: {value}')
    resolved = (ROOT / path).resolve()
    require(resolved.is_relative_to(ROOT), f'Path leaves repository: {value}')
    return resolved


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_image(path, expected_size, crop_size, profile):
    with Image.open(path) as image:
        image.load()  # Decode completely, so truncated JPEGs are caught.
        require(image.format == 'JPEG' and image.mode == 'RGB', 'Expected RGB JPEG')
        require(image.size == expected_size, f'Expected {expected_size}, got {image.size}')
        w, h = image.size
        require(w * 9 == h * 16, 'Image is not exactly 16:9')
        require(w <= crop_size[0] and h <= crop_size[1], 'Image was upscaled')
        exif = image.getexif()
        require(set(exif) == {305, 315, 33432}, 'Unexpected or missing EXIF fields')
        require(exif[315] == AUTHOR, 'Incorrect photographer credit')
        require(exif[33432] == f'Copyright 2026 {AUTHOR}. All rights reserved.',
                'Incorrect copyright attribution')
        require(not (set(image.info) - ALLOWED_INFO), 'Unexpected embedded metadata')
        require(image.info.get('icc_profile') == profile, 'Incorrect embedded sRGB profile')
        # An EXIF thumbnail lives in a second IFD, outside getexif()'s main tags.
        tiff = image.info['exif'][6:]
        order = '<' if tiff[:2] == b'II' else '>'
        offset = struct.unpack_from(order + 'I', tiff, 4)[0]
        count = struct.unpack_from(order + 'H', tiff, offset)[0]
        next_ifd = struct.unpack_from(order + 'I', tiff, offset + 2 + count * 12)[0]
        require(next_ifd == 0, 'Unexpected embedded EXIF thumbnail/IFD')


def check_colors(path):
    with path.open('rb') as file:
        colors = tomllib.load(file)
    require(bool(colors), 'Empty colors.toml')

    def visit(values):
        for name, value in values.items():
            if isinstance(value, dict):
                visit(value)
            elif name == 'mode':
                require(value in {'dark', 'light'}, f'Invalid theme mode: {value!r}')
            else:
                require(isinstance(value, str) and HEX.fullmatch(value),
                        f'Invalid color {name}: {value!r}')
    visit(colors)


def main():
    errors = []
    recipes_doc = json.loads((ROOT / 'metadata/recipes.json').read_text())
    collection = json.loads((ROOT / 'metadata/collection.json').read_text())
    recipes_list = recipes_doc['wallpapers']
    photos = collection['wallpapers']
    require(recipes_doc['author'] == collection['author'] == AUTHOR, 'Incorrect collection author')
    require(collection['aspect_ratio'] == '16:9', 'Incorrect collection aspect ratio')
    recipes = {r['slug']: r for r in recipes_list}
    entries = {p['slug']: p for p in photos}
    require(len(recipes) == len(recipes_list), 'Duplicate recipe slugs')
    require(len(entries) == len(photos), 'Duplicate collection slugs')
    require(bool(recipes) and recipes.keys() == entries.keys(), 'Recipe/collection slugs differ')
    profile_path = ROOT / 'profiles/sRGB.icc'
    profile = profile_path.read_bytes()
    require('sRGB' in ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(str(profile_path))),
            'Bundled profile is not sRGB')
    expected_files = set()

    for slug, photo in entries.items():
        try:
            require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug), 'Invalid slug')
            recipe = recipes[slug]
            for field in ('title', 'theme', 'description', 'source'):
                require(photo[field] == recipe[field], f'Recipe mismatch: {field}')
            require(photo['photographer'] == AUTHOR, 'Incorrect collection photo credit')
            source = recipe['source']
            require(re.fullmatch(r'[0-9a-f]{64}', source['sha256']), 'Invalid source checksum')
            require(source['collection'] in {'pictures', 'ventoy'}, 'Unknown source collection')
            require(not Path(source['file']).is_absolute() and '..' not in Path(source['file']).parts,
                    'Unsafe source-relative path')
            x1, y1, x2, y2 = recipe['crop_px']
            require(all(type(v) is int for v in (x1, y1, x2, y2)), 'Crop coordinates must be integers')
            require(0 <= x1 < x2 <= source['width'] and 0 <= y1 < y2 <= source['height'],
                    'Crop exceeds recorded source dimensions')
            crop = (x2 - x1, y2 - y1)
            require(crop[0] * 9 == crop[1] * 16, 'Crop is not exactly 16:9')
            master_size = (photo['width'], photo['height'])
            require(master_size == (min(3840, crop[0]), min(2160, crop[1])),
                    'Master dimensions do not match the recorded crop/export size')
            paths = {'master': f'wallpapers/master/{slug}.jpg',
                     'fullhd': f'wallpapers/1920x1080/{slug}.jpg',
                     'preview': f'previews/{slug}.jpg'}
            sizes = {'master': master_size, 'fullhd': (1920, 1080), 'preview': (640, 360)}
            for kind, expected_path in paths.items():
                require(photo[kind] == expected_path, f'Unexpected {kind} path')
                path = repo_path(photo[kind])
                expected_files.add(path)
                check_image(path, sizes[kind], crop, profile)
            require(master_size[0] >= 1920 and master_size[1] >= 1080,
                    'Master is smaller than Full HD')
            require(sha256(repo_path(photo['master'])) == photo['sha256'], 'Master checksum mismatch')
        except (KeyError, OSError, ValueError, TypeError, struct.error) as error:
            errors.append(f'{slug}: {error}')

    actual_files = set()
    for folder in ('wallpapers/master', 'wallpapers/1920x1080', 'previews'):
        actual_files.update(path.resolve() for path in (ROOT / folder).glob('*.jpg')
                            if path.name != 'collection.jpg')
    if actual_files != expected_files:
        missing = sorted(str(p.relative_to(ROOT)) for p in expected_files - actual_files)
        extra = sorted(str(p.relative_to(ROOT)) for p in actual_files - expected_files)
        errors.append(f'Export file set differs; missing={missing}, extra={extra}')

    theme_count = 0
    for name in sorted({p['theme'] for p in photos}):
        try:
            theme = repo_path(f'themes/{name}')
            require(theme.is_dir(), 'Theme directory is missing')
            colors = theme / 'colors.toml'
            require(colors.is_file(), 'colors.toml is missing')
            check_colors(colors)
            require((theme / 'hyprland.lua').is_file(), 'hyprland.lua is missing')
            backgrounds = list((theme / 'backgrounds').iterdir())
            require(bool(backgrounds), 'No theme backgrounds')
            expected_backgrounds = {repo_path(p['fullhd']) for p in photos if p['theme'] == name}
            require(len(backgrounds) == len(expected_backgrounds), 'Incorrect background count')
            for path in backgrounds:
                require(path.is_symlink() and path.is_file(), f'Missing or broken background link: {path.name}')
            require({p.resolve() for p in backgrounds} == expected_backgrounds,
                    'Background links do not exactly match this theme’s Full HD photos')
            theme_count += 1
        except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as error:
            errors.append(f'theme {name}: {error}')

    if errors:
        for error in errors:
            print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(f'OK: {len(photos)} wallpapers, {len(expected_files)} exports, {theme_count} themes. '
          'Dimensions, crops, checksums, credits, metadata, ICC and background links verified.')
    print('Original files are not required. Source records match recipes; original-file contents are not checked.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError, TypeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
