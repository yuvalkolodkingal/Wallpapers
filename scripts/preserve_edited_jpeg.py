#!/usr/bin/env python3
"""Publish a finished JPEG edit without recompressing its master.

Only fresh attribution, reviewed sRGB ICC and thumbnail-free JFIF/canonical
Adobe decoding metadata survive. Image coding segments and every entropy scan
remain byte-for-byte unchanged. This does not create a collection entry.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import struct
import tempfile

from PIL import Image, ImageCms

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = 'Yuval Kolodkin-Gal'
COPYRIGHT = f'Copyright 2026 {AUTHOR}. All rights reserved.'
MODE = 'preserve-existing-edited-jpeg'
SOFTWARE = 'Existing JPEG edit preserved; attribution only'
DOWNSAMPLE_SOFTWARE = 'Existing edit downsampled locally with Pillow'
REVIEWED_SOFTWARE = (SOFTWARE, DOWNSAMPLE_SOFTWARE,
                     'GIMP 3.0.4; local photographic editing')
MAX_BYTES = 32 * 1024 * 1024
# Exact, inspected standard profiles. An arbitrary ICC can contain private text;
# a declared checksum alone is not permission to retain an unreviewed profile.
REVIEWED_SRGB_PROFILES = frozenset({
    'a2724f5142df7c7154bc4f0cb517982cd55e252260abd965e7553566b915a7c2',
    '12afb4d9953adee0607d347daee5b78b18d6b3cab2d572b88970703f5edb37bc',
})


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Part:
    marker: int | None
    data: bytes
    payload: bytes = b''


def segments(data: bytes) -> tuple[list[Part], int]:
    """Parse all baseline/progressive scans, including inter-scan metadata."""
    if len(data) > MAX_BYTES or not data.startswith(b'\xff\xd8'):
        raise ValueError('Expected a JPEG of at most 32 MiB')
    parts = [Part(0xd8, data[:2])]
    pos = 2
    scans = 0
    while pos < len(data):
        start = pos
        if data[pos] != 0xff:
            raise ValueError('Expected a JPEG marker')
        while pos < len(data) and data[pos] == 0xff:
            pos += 1
        if pos == len(data):
            raise ValueError('Truncated JPEG marker')
        marker = data[pos]
        pos += 1
        if marker == 0xd9:
            if not scans:
                raise ValueError('JPEG contains no image scan')
            parts.append(Part(marker, data[start:pos]))
            return parts, len(data) - pos
        if marker in {0x00, 0x01, 0xd8, *range(0xd0, 0xd8)} or marker < 0xc0:
            raise ValueError('Unsupported or misplaced JPEG marker')
        if pos + 2 > len(data):
            raise ValueError('Truncated JPEG segment length')
        length = struct.unpack_from('>H', data, pos)[0]
        if length < 2 or pos + length > len(data):
            raise ValueError('Invalid or truncated JPEG segment')
        end = pos + length
        parts.append(Part(marker, data[start:end], data[pos + 2:end]))
        pos = end
        if marker != 0xda:
            continue
        scans += 1
        start = pos
        while True:
            prefix = data.find(b'\xff', pos)
            if prefix == -1:
                raise ValueError('Missing JPEG end marker')
            following = prefix + 1
            while following < len(data) and data[following] == 0xff:
                following += 1
            if following == len(data):
                raise ValueError('Truncated JPEG entropy scan')
            if data[following] == 0x00 or 0xd0 <= data[following] <= 0xd7:
                pos = following + 1
                continue
            parts.append(Part(None, data[start:prefix]))
            pos = prefix
            break
    raise ValueError('Missing JPEG end marker')


def coding_bytes(parts: list[Part]) -> bytes:
    return b''.join(p.data for p in parts
                    if p.marker is None or not (0xe0 <= p.marker <= 0xef or p.marker == 0xfe))


def check_orientation(payload: bytes) -> None:
    """Inspect only IFD0's orientation; never follow private nested EXIF IFDs."""
    if not payload.startswith(b'Exif\0\0'):
        return
    tiff = payload[6:]
    if len(tiff) < 8 or tiff[:2] not in {b'II', b'MM'}:
        raise ValueError('Malformed EXIF header')
    order = '<' if tiff[:2] == b'II' else '>'
    if struct.unpack_from(order + 'H', tiff, 2)[0] != 42:
        raise ValueError('Malformed EXIF TIFF header')
    offset = struct.unpack_from(order + 'I', tiff, 4)[0]
    if offset < 8 or offset + 2 > len(tiff):
        raise ValueError('Malformed EXIF IFD0')
    count = struct.unpack_from(order + 'H', tiff, offset)[0]
    if offset + 2 + count * 12 + 4 > len(tiff):
        raise ValueError('Truncated EXIF IFD0')
    seen = False
    for index in range(count):
        entry = offset + 2 + index * 12
        tag, kind, amount = struct.unpack_from(order + 'HHI', tiff, entry)
        if tag == 274:
            if seen or kind != 3 or amount != 1 or struct.unpack_from(order + 'H', tiff, entry + 8)[0] != 1:
                raise ValueError('Finished JPEG must already be oriented (EXIF Orientation=1)')
            seen = True


def icc_profile(parts: list[Part]) -> bytes:
    chunks = {}
    total = None
    for part in parts:
        if part.marker != 0xe2 or not part.payload.startswith(b'ICC_PROFILE\0'):
            continue
        if len(part.payload) < 14:
            raise ValueError('Truncated ICC chunk')
        index, count = part.payload[12:14]
        if not (1 <= index <= count) or index in chunks or (total is not None and count != total):
            raise ValueError('Ambiguous or invalid ICC chunk sequence')
        total = count
        chunks[index] = part.payload[14:]
    if total is None or set(chunks) != set(range(1, total + 1)):
        raise ValueError('A complete reviewed sRGB profile is required')
    profile = b''.join(chunks[i] for i in range(1, total + 1))
    if digest(profile) not in REVIEWED_SRGB_PROFILES:
        raise ValueError('ICC profile is not an inspected metadata-safe sRGB profile')
    cms = ImageCms.ImageCmsProfile(BytesIO(profile))
    if cms.profile.xcolor_space.strip() != 'RGB' or 'srgb' not in ImageCms.getProfileDescription(cms).lower():
        raise ValueError('ICC profile is not sRGB')
    return profile


def attribution(software: str = SOFTWARE) -> bytes:
    exif = Image.Exif()
    exif[305] = software
    exif[315] = AUTHOR
    exif[33432] = COPYRIGHT
    return exif.tobytes()


def marker_bytes(marker: int, payload: bytes) -> bytes:
    return bytes((0xff, marker)) + struct.pack('>H', len(payload) + 2) + payload


def preserved_master(data: bytes, expected_sha256: str) -> tuple[bytes, dict]:
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256) or digest(data) != expected_sha256:
        raise ValueError('Source checksum changed')
    parts, trailing = segments(data)
    coding_markers = {0xd8, 0xd9, 0xc0, 0xc2, 0xc4, 0xdb, 0xdd, 0xda}
    if any(p.marker is not None and p.marker not in coding_markers
           and not (0xe0 <= p.marker <= 0xef or p.marker == 0xfe) for p in parts):
        raise ValueError('Unsupported JPEG coding marker')
    frames = [p for p in parts if p.marker in {0xc0, 0xc2}]
    unsupported_frames = [p for p in parts if p.marker in set(range(0xc0, 0xd0)) - {0xc0, 0xc2, 0xc4}]
    if len(frames) != 1 or unsupported_frames or len(frames[0].payload) != 15:
        raise ValueError('Expected one baseline or progressive RGB JPEG frame')
    precision, height, width, components = struct.unpack_from('>BHHB', frames[0].payload)
    if precision != 8 or components != 3 or not (0 < width <= 3840 and 0 < height <= 2160) or width * 9 != height * 16:
        raise ValueError('Finished JPEG must be RGB, exactly 16:9 and at most 3840x2160')
    profile = icc_profile(parts)
    exif_parts = [p for p in parts if p.marker == 0xe1]
    # Equality to fresh trusted serialization excludes private unused bytes,
    # alternate IFDs, thumbnails and nonzero padding as well as extra tags.
    existing_attribution = (exif_parts[0] if len(exif_parts) == 1
                            and exif_parts[0].payload in {attribution(s) for s in REVIEWED_SOFTWARE}
                            else None)
    output = [parts[0].data]
    if existing_attribution is None:
        output.append(marker_bytes(0xe1, attribution()))
    removed = 0
    for part in parts[1:]:
        marker = part.marker
        if marker == 0xe1:
            check_orientation(part.payload)
        if part is existing_attribution:
            output.append(part.data)
        elif marker == 0xe2 and part.payload.startswith(b'ICC_PROFILE\0'):
            output.append(part.data)
        elif marker == 0xe0 and part.payload.startswith(b'JFIF\0'):
            if (len(part.payload) < 14 or part.payload[5:7] not in {b'\x01\x00', b'\x01\x01', b'\x01\x02'}
                    or part.payload[7] not in {0, 1, 2}
                    or len(part.payload) != 14 + 3 * part.payload[12] * part.payload[13]):
                raise ValueError('Malformed JFIF thumbnail')
            # Preserve the decoding header/density, discard any embedded thumbnail.
            output.append(part.data if not (part.payload[12] or part.payload[13])
                          else marker_bytes(marker, part.payload[:12] + b'\0\0'))
            removed += int(bool(part.payload[12] or part.payload[13]))
        elif marker == 0xee:
            if len(part.payload) != 12 or not part.payload.startswith(b'Adobe') or part.payload[11] not in {0, 1}:
                raise ValueError('Unsupported Adobe decoding metadata')
            output.append(part.data)
        elif marker is not None and (0xe0 <= marker <= 0xef or marker == 0xfe):
            removed += 1
        else:
            output.append(part.data)
    master = b''.join(output)
    master_parts, master_trailing = segments(master)
    if master_trailing or coding_bytes(master_parts) != coding_bytes(parts) or icc_profile(master_parts) != profile:
        raise ValueError('Preservation changed JPEG coding bytes or ICC')
    with Image.open(BytesIO(master)) as im:
        im.load()
        if im.format != 'JPEG' or im.mode != 'RGB' or im.size != (width, height):
            raise ValueError('JPEG decoder disagrees with its frame')
        pixel_sha256 = digest(im.tobytes())
    with Image.open(BytesIO(data)) as original:
        original.load()
        if original.mode != 'RGB' or original.size != (width, height) or digest(original.tobytes()) != pixel_sha256:
            raise ValueError('Preservation changed decoded image pixels')
    return master, {
        'processing': MODE,
        'source_sha256': digest(data),
        'master_sha256': digest(master),
        'master_bytes_preserved': master == data,
        'existing_attribution_preserved': existing_attribution is not None,
        'width': width, 'height': height,
        'icc_sha256': digest(profile),
        'jpeg_coding_sha256': digest(coding_bytes(parts)),
        'decoded_pixel_sha256': pixel_sha256,
        'removed_metadata_segments': removed,
        'discarded_trailing_bytes': trailing,
    }


def build_exports(data: bytes, expected_sha256: str, *, fullhd: bool = False,
                  preview: bool = False) -> tuple[dict[str, bytes], dict]:
    """Prepare every requested output before any filesystem writes."""
    master, receipt = preserved_master(data, expected_sha256)
    width, height = receipt['width'], receipt['height']
    sizes = {}
    if fullhd:
        sizes['fullhd'] = (1920, 1080)
    if preview:
        sizes['preview'] = (640, 360)
    for size in sizes.values():
        if width < size[0] or height < size[1]:
            raise ValueError(f'Cannot export {size[0]}x{size[1]} without upscaling')
    exports = {'master': master}
    profile = icc_profile(segments(master)[0])
    with Image.open(BytesIO(master)) as im:
        im.load()
        for kind, size in sizes.items():
            if im.size == size:
                exports[kind] = master
                continue
            output = BytesIO()
            im.resize(size, Image.Resampling.LANCZOS).save(
                output, format='JPEG', quality=93 if kind == 'fullhd' else 86,
                subsampling=0, optimize=True,
                exif=attribution(DOWNSAMPLE_SOFTWARE),
                icc_profile=profile)
            exports[kind] = output.getvalue()
    receipt['exports'] = {
        kind: {'sha256': digest(blob), 'bytes': len(blob),
               'width': width if kind == 'master' else sizes[kind][0],
               'height': height if kind == 'master' else sizes[kind][1]}
        for kind, blob in exports.items()
    }
    return exports, receipt


def write_exports(data: bytes, expected_sha256: str, targets: dict[str, Path],
                  *, source_path: Path | None = None, keep_existing_master: bool = False) -> dict:
    if 'master' not in targets or set(targets) - {'master', 'fullhd', 'preview'}:
        raise ValueError('Expected master and optional fullhd/preview outputs')
    directories = {'master': ROOT / 'wallpapers/master',
                   'fullhd': ROOT / 'wallpapers/1920x1080', 'preview': ROOT / 'previews'}
    resolved = {kind: path.resolve() for kind, path in targets.items()}
    if len(set(resolved.values())) != len(resolved):
        raise ValueError('Output paths must differ')
    shared_source = source_path is not None and source_path.resolve() in set(resolved.values())
    if shared_source and (not keep_existing_master or source_path.resolve() != resolved['master']):
        raise ValueError('Source photographs must remain untouched')
    for kind, path in resolved.items():
        directory = directories[kind]
        parents = [directory, *directory.parents]
        redirected = any(parent.is_symlink() for parent in parents[:parents.index(ROOT) + 1])
        if (redirected or not directory.resolve().is_relative_to(ROOT.resolve())
                or path.parent != directory.resolve() or path.suffix != '.jpg' or targets[kind].is_symlink()):
            raise ValueError('Exports must be regular JPEGs in their repository output directories')
    exports, receipt = build_exports(data, expected_sha256,
                                    fullhd='fullhd' in targets, preview='preview' in targets)
    if shared_source:
        if exports['master'] != data or source_path.read_bytes() != data:
            raise ValueError('Existing source master would be changed')
    for kind, blob in exports.items():
        if kind == 'master' and shared_source:
            continue  # A published exact-copy source is read only, never rewritten.
        path = resolved[kind]
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.edited-jpeg-', delete=False) as file:
            temporary = Path(file.name)
            try:
                file.write(blob)
                file.flush()
                os.fchmod(file.fileno(), 0o644)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--sha256', required=True, help='Exact SHA-256 of the finished input JPEG')
    parser.add_argument('--master', required=True, type=Path)
    parser.add_argument('--fullhd', type=Path)
    parser.add_argument('--preview', type=Path)
    args = parser.parse_args()
    targets = {kind: value for kind in ('master', 'fullhd', 'preview')
               if (value := getattr(args, kind)) is not None}
    if args.source.resolve() in {path.resolve() for path in targets.values()}:
        parser.error('Source photographs must remain untouched')
    try:
        receipt = write_exports(args.source.read_bytes(), args.sha256, targets, source_path=args.source)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
