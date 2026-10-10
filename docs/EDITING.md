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
The original set contains 18 distinct selections; duplicate copies across Pictures
and Ventoy are represented once. Near-identical burst frames, weaker focus,
overexposed variants, and distracting compositions were left out.

The collection favors nature detail, wildlife, quiet garden scenes, and evening
light. Rose City keeps the photographer's existing pink/violet interpretation
of a deliberately soft-looking city image. Its source is already graded, which
is recorded in `metadata/recipes.json`. The other selections start from camera
JPEGs, including the JPEGs stored in a folder named `RAW`.

**Ember Clouds, City Silhouette** is the nineteenth selection. The photographer
supplied the completed GIMP 3.0.4 edit of IMG_2775 as a 2048×1152 JPEG. Its exact
SHA-256 is `7af8cb5ce0d87773109d759afdd1d14ef22ce7e84fdc1533da1539083cd11b0b`.
The camera-original bytes were not supplied, so no camera-original checksum or
invented RAW recipe is recorded. Its finished edit is preserved byte for byte,
including the existing artist/copyright/GIMP credit and reviewed sRGB profile;
only its 1920×1080 and 640×360 derivatives are downsampled locally.

Nine more supplied JPEGs were added in October 2026: Stone and Branches,
Jellyfish Drift, Night Shore, Summer Spirals, Moray in Shelter, Sand and Sky,
Golden Lichen, Seedpod Still Life, and Lavender Light. These are the supplied
WhatsApp-sized files, not unprovided full-resolution camera originals. Their
actual byte hashes and dimensions are recorded under `uploads`. The supplied
lion photo was excluded at the photographer's request.

## Processing

`metadata/recipes.json` records the original relative filename, SHA-256 checksum,
auto-oriented pixel crop, and every adjustment. Source paths in this public repo
are relative to their input roots; the complete local inventory stays private.
Camera inputs use `pictures` or `ventoy`; completed JPEG edits use `edited`.
The newly supplied originals use `uploads`, resolved by `--uploads-root`.

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

Twenty-one wallpapers have a 1920×1080 version. Sixteen have 3840×2160 masters.
The two square-source crops, Last Amber and Pink Berry, have 2992×1683 masters.
Ember Clouds, City Silhouette retains its 2048×1152 finished master. Jellyfish
Drift and Night Shore have 2032×1143 and 2048×1152 masters. The other seven new
photos retain crops between 1136×639 and 1600×900; `fullhd` is `null` for these
entries. Gallery downloads and theme backgrounds use their masters. Nothing
is upscaled, including the 640×360 previews.
The original photographs' optical softness and clipped highlights
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
exactly 16:9, inside the source boundaries, and at least 640×360 for a preview.
Ordinary photos smaller than 1920×1080 produce a master and preview only. The renderer
checks source hashes so an unexpected input file does not silently replace the
original. To deliberately adopt a replacement input, update its source checksum,
source dimensions, and crop in the recipe first.

The bundled `profiles/sRGB.icc` is a fixed sRGB output profile. Keeping its creation
time stable also makes unchanged renders produce identical JPEG bytes under the
locked dependency versions.

### Preserve a completed JPEG edit

For an already finished JPEG, use the explicit recipe value
`"processing": "preserve-existing-edited-jpeg"`, with `"adjustments": {}` and a
crop covering the entire image. The renderer sends this mode through
`scripts/preserve_edited_jpeg.py`; it does not grade, sharpen, crop, rotate or
recompress the master. Record the input checksum in the recipe and the separate
published master checksum in the collection: inserting attribution changes the
file checksum even though every decoded pixel and JPEG coding byte is preserved.
If the original JPEG already has the exact reviewed three-tag attribution
serialization, thumbnail-free decoding headers and no private metadata, the
entire file is preserved, including its checksum. The known GIMP software credit
is retained only on exact equality to a fresh trusted attribution block; extra
IFDs, hidden text, nonzero padding or arbitrary software strings cannot pass.

The preservation utility can also prepare exports without changing recipes,
the collection, theme links or gallery:

```sh
uv run scripts/preserve_edited_jpeg.py \
  --source /path/to/finished-edit.jpg --sha256 EXACT_INPUT_SHA256 \
  --master wallpapers/master/example.jpg \
  --fullhd wallpapers/1920x1080/example.jpg --preview previews/example.jpg
```

`--fullhd` and `--preview` are optional, but a requested derivative must fit
inside the input dimensions. This specialized completed-edit preservation mode still requires a
genuine 1920×1080 derivative; a smaller finished edit fails before any exports
are written. Ordinary uploaded photographs support smaller masters. The JPEG must already be RGB, exactly 16:9, no larger than 3840×2160,
and oriented without a nontrivial EXIF Orientation tag. Only baseline and
progressive JPEG coding are supported. Downsampled derivatives use Lanczos and
fresh JPEG encoding; only the master preserves the original coding bytes.

Original EXIF (including nested GPS, maker notes and thumbnails), XMP, IPTC,
comments, unknown application metadata and trailing bytes are removed across
all scans. New EXIF contains only Artist, Copyright and processing-software
credit. Thumbnail-free JFIF and canonical Adobe decoding headers are retained.
The original ICC chunks remain unchanged; only the exact inspected bundled
sRGB profile and the standard compact sRGB profile with SHA-256
`12afb4d9953adee0607d347daee5b78b18d6b3cab2d572b88970703f5edb37bc`
are accepted. Other profiles fail closed until their metadata has been reviewed;
an arbitrary ICC can itself contain private text. This preserves ordinary
photographic image data, not a guarantee against information hidden in pixels
or image coding data.

Finished edits use the source collection `edited`, with their actual edited
filename and checksum. To reproduce an edit from a separately saved input:

```sh
uv run scripts/render_wallpapers.py \
  --pictures-root /path/to/Pictures --ventoy-root /path/to/DCIM \
  --edited-root /path/to/finished-edits --only ember-clouds-city-silhouette
```

Without `--edited-root`, the renderer uses the exact published master as the
recovery source and never rewrites it. Its recorded checksum must still match:

```sh
uv run scripts/render_wallpapers.py \
  --pictures-root unused --ventoy-root unused --only ember-clouds-city-silhouette
```

The utility emits checksums, dimensions, coding/pixel identity evidence and
metadata-removal counts. Its output paths are restricted to repository export
directories, and source photographs must remain untouched. Adding a preserved
edit to the collection also requires explicit verifier support for its reviewed
ICC; this utility alone does not relax the existing collection's ICC rules.

### Reproduce the uploaded photographs

Keep the original uploaded JPEG filenames in a local source directory. For example:

```sh
uv run scripts/render_wallpapers.py \
  --pictures-root unused --ventoy-root unused \
  --uploads-root /path/to/uploaded-photos --only stone-and-branches jellyfish-drift \
  night-shore summer-spirals moray-in-shelter sand-and-sky golden-lichen \
  seedpod-still-life lavender-light
uv run scripts/build_overview.py
uv run scripts/build_gallery.py
uv run scripts/verify_collection.py
```

These edits use small exposure, contrast, white-balance, saturation, shadow and
highlight adjustments plus mild sharpening. The portrait moray image is cropped
around the eye and mouth for the collection's desktop format. Night Shore keeps
its original diagonal composition and dark sky. No objects were added or removed.
