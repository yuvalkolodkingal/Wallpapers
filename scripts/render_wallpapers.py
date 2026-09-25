#!/usr/bin/env python3
"""Reproduce the selected photo grades and crops from the owner's source files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageCms, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = 'Yuval Kolodkin-Gal'
# Bundled profile fixes its creation timestamp, so rerenders are byte-stable.
ICC = (ROOT / 'profiles/sRGB.icc').read_bytes()

def srgb_to_linear(a):
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4)

def linear_to_srgb(a):
    a = np.maximum(a, 0)
    return np.where(a <= .0031308, 12.92 * a, 1.055 * a ** (1 / 2.4) - .055)

def grade(im, p):
    """Conservative local processing; no scene synthesis, removal or replacement."""
    a = np.asarray(im, dtype=np.float32) / 255
    lin = srgb_to_linear(a)
    lin *= 2 ** p.get('exposure_ev', 0)
    lin *= np.array(p.get('white_balance_rgb', [1, 1, 1]), dtype=np.float32)
    # Luminance-weighted masks keep highlight/shadow changes smooth.
    lum = np.sum(lin * np.array([.2126, .7152, .0722]), axis=2, keepdims=True)
    shadow = p.get('shadow_lift', 0)
    lin *= 1 + shadow * np.exp(-lum / .16)
    strength = p.get('highlight_compression', 0)
    lin /= 1 + strength * np.maximum(lum - .30, 0)
    a = np.clip(linear_to_srgb(lin), 0, 1)
    # S-curve with anchored black/white points.
    contrast = p.get('contrast', 0)
    a += contrast * (a - .5) * a * (1 - a)
    gray = np.sum(a * np.array([.2126, .7152, .0722]), axis=2, keepdims=True)
    saturation = p.get('saturation', 1)
    a = gray + saturation * (a - gray)
    a = np.clip(a, 0, 1)
    return Image.fromarray(np.rint(a * 255).astype('uint8'))

def load_srgb(path):
    with Image.open(path) as raw:
        im = ImageOps.exif_transpose(raw)
        profile = raw.info.get('icc_profile')
        if profile:
            import io
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile('sRGB'), outputMode='RGB')
        else:
            im = im.convert('RGB')
        return im.copy()

def export_jpeg(im, path, quality, sharpening):
    if sharpening:
        im = im.filter(ImageFilter.UnsharpMask(radius=.7, percent=sharpening, threshold=3))
    # Fresh metadata deliberately omits source GPS, dates, serials and thumbnails.
    exif = Image.Exif()
    exif[315] = AUTHOR
    exif[33432] = f'Copyright 2026 {AUTHOR}. All rights reserved.'
    exif[305] = 'Local photographic processing: Pillow + NumPy'
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=quality, subsampling=0, optimize=True, exif=exif, icc_profile=ICC)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pictures-root', type=Path, required=True)
    parser.add_argument('--ventoy-root', type=Path, required=True)
    parser.add_argument('--only', nargs='*', help='Render only these slugs; collection metadata still includes all existing exports.')
    args = parser.parse_args()
    roots = {'pictures': args.pictures_root, 'ventoy': args.ventoy_root}
    recipes = json.loads((ROOT / 'metadata/recipes.json').read_text())
    if args.only is not None:
        unknown = set(args.only) - {r['slug'] for r in recipes['wallpapers']}
        if unknown:
            parser.error(f'Unknown wallpaper slugs: {sorted(unknown)}')
    entries = []
    for r in recipes['wallpapers']:
        slug = r['slug']
        source = r['source']
        src = roots[source['collection']] / source['file']
        master = ROOT / f'wallpapers/master/{slug}.jpg'
        hd = ROOT / f'wallpapers/1920x1080/{slug}.jpg'
        preview = ROOT / f'previews/{slug}.jpg'
        if args.only is None or slug in args.only:
            sha = hashlib.sha256(src.read_bytes()).hexdigest()
            if sha != source['sha256']:
                raise SystemExit(f'Source checksum changed: {source["file"]}')
            im = load_srgb(src)
            box = r['crop_px']
            if not (0 <= box[0] < box[2] <= im.width and 0 <= box[1] < box[3] <= im.height):
                raise SystemExit(f'Invalid crop: {slug}')
            im = im.crop(tuple(box))
            if im.width * 9 != im.height * 16:
                raise SystemExit(f'Crop is not exactly 16:9: {slug}')
            im = grade(im, r['adjustments'])
            size = (min(3840, im.width), min(2160, im.height))
            if size[0] < 1920 or size[1] < 1080:
                raise SystemExit(f'Selected source is too small: {slug}')
            master_im = im.resize(size, Image.Resampling.LANCZOS)
            sharp = r['adjustments'].get('sharpen_percent', 25)
            export_jpeg(master_im, master, 94, sharp)
            export_jpeg(master_im.resize((1920,1080), Image.Resampling.LANCZOS), hd, 93, sharp)
            export_jpeg(master_im.resize((640,360), Image.Resampling.LANCZOS), preview, 86, 10)
            print(f'{slug}: {size[0]}x{size[1]} + 1920x1080', flush=True)
        if not master.exists():
            continue
        with Image.open(master) as im:
            w,h = im.size
        entries.append({**{k:r[k] for k in ['slug','title','theme','description']},
                        'source': source, 'master': str(master.relative_to(ROOT)),
                        'fullhd': str(hd.relative_to(ROOT)), 'preview':str(preview.relative_to(ROOT)),
                        'width':w, 'height':h, 'sha256':hashlib.sha256(master.read_bytes()).hexdigest(),
                        'photographer': AUTHOR})
    (ROOT / 'metadata/collection.json').write_text(json.dumps({'author':AUTHOR,'aspect_ratio':'16:9','wallpapers':entries},indent=2)+'\n')

if __name__ == '__main__':
    main()
