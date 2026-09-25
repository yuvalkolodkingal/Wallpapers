# Editing notes

All photographs were taken by **Yuval Kolodkin-Gal**. This collection uses local
photographic adjustments only. No generative edits, object replacement, or AI
redrawing were used. The original source files and existing RawTherapee `.pp3`
sidecars remain unchanged in the owner's source folders.

## Selection

Reviewed 142 camera images from the Ventoy DCIM directory and 84 raster images
from Pictures (226 files, 214 unique file hashes). Pictures includes 18 photo,
wallpaper, and screenshot entries plus 66 unrelated video-project graphics,
profile images, and editing previews. Those project graphics are excluded.
The final set contains 18 distinct selections; duplicate copies across Pictures
and Ventoy are represented once. Near-identical burst frames, weaker focus,
overexposed variants, and distracting compositions were left out.

The collection favors nature detail, wildlife, quiet garden scenes, and evening
light. Rose City keeps the photographer's existing pink/violet interpretation
of a deliberately soft-looking city image. Its source is already graded, which
is recorded in `metadata/recipes.json`. The other selections start from camera
JPEGs, including the JPEGs stored in a folder named `RAW`.

## Processing

`metadata/recipes.json` records the original relative filename, SHA-256 checksum,
auto-oriented pixel crop, and every adjustment. Source paths in this public repo
are relative to the two input roots; the complete local inventory stays private.

The renderer converts embedded color profiles to sRGB, applies exposure and
white-balance gains in linear light, uses smooth luminance masks for shadows and
highlights, and applies a restrained contrast curve and saturation adjustment.
It uses Lanczos resizing and mild output sharpening where useful. Featherlines
and Rose City receive no output sharpening. Every export is exactly 16:9.

- **Last Amber:** crop starts below the power lines, preserving the original skyline.
- **Featherlines:** crop emphasizes the feather texture and shaft. Natural color
  fringing remains in fine detail; sharpening is disabled to avoid amplifying it.
- **Bottlebrush:** reduce saturation and the blue channel's white-balance gain
  to moderate the original cyan cast while preserving the crimson flowers.
- **City Afterglow:** remove excess foreground, gently lift the darkest buildings,
  and keep the sky's warm/cool balance.
- **Wildlife and foliage:** restrained shadow lifts, highlight compression, and
  color adjustments preserve feather, leaf, and petal detail.

All wallpapers have a 1920×1080 version. Sixteen have 3840×2160 masters. The two
square-source crops, Last Amber and Pink Berry, have 2992×1683 masters. Nothing is
upscaled. The original photographs' optical softness and clipped highlights
cannot be reconstructed by these adjustments.

JPEGs use high-quality 4:4:4 encoding with an embedded sRGB profile. New EXIF
contains only Artist, Copyright, and processing-software credit; original GPS,
capture time, device serial, and thumbnail metadata are not copied.

## Reproduce or revise

Python 3.12+ and `uv` are needed for photo rendering; the theme installer needs
only Python's standard library. Source photographs are intentionally not
duplicated into the public repository.

```sh
uv sync --locked
uv run scripts/render_wallpapers.py \
  --pictures-root "$HOME/Pictures" \
  --ventoy-root "/path/to/Canon Powershop DCIM"
uv run scripts/build_overview.py
python3 scripts/build_gallery.py
```

Edit a recipe's values and rerender just that wallpaper with `--only SLUG`.
The crop is `[left, top, right, bottom]` in auto-oriented source pixels. Keep it
exactly 16:9, inside the source boundaries, and at least 1920×1080. The renderer
checks source hashes so an unexpected input file does not silently replace the
original. To deliberately adopt a replacement input, update its source checksum,
source dimensions, and crop in the recipe first.

The bundled `profiles/sRGB.icc` is a fixed sRGB output profile. Keeping its creation
time stable also makes unchanged renders produce identical JPEG bytes under the
locked dependency versions.
