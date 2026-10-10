"""Finished-edit controls: actual JPEG decoding, scans and metadata privacy."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import preserve_edited_jpeg as preserve
import render_wallpapers as renderer
import verify_collection as verifier

PROFILE = (ROOT / 'profiles/sRGB.icc').read_bytes()
PRIVATE = b'PRIVATE_LOCATION_DEVICE_DATE_TRANSCRIPT'


def jpeg(*, size=(1280, 720), progressive=False, exif=b''):
    image = Image.new('RGB', size, '#bd592c')
    # Nonconstant detail makes preserved/downsampled pixel comparisons useful.
    for x in range(0, size[0], 17):
        for y in range(0, size[1], 19):
            image.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    output = BytesIO()
    image.save(output, format='JPEG', quality=91, progressive=progressive,
               icc_profile=PROFILE, exif=exif)
    return output.getvalue()


def marker(code, payload):
    return bytes([255, code]) + (len(payload) + 2).to_bytes(2, 'big') + payload


def independent_parts(data):
    """Separate test reader returns the actual full marker/entropy stream."""
    records = [(0xd8, data[:2])]
    cursor = 2
    while cursor < len(data):
        begin = cursor
        while data[cursor] == 255:
            cursor += 1
        code = data[cursor]
        cursor += 1
        if code == 0xd9:
            records.append((code, data[begin:cursor]))
            return records
        length = int.from_bytes(data[cursor:cursor + 2], 'big')
        cursor += length
        records.append((code, data[begin:cursor]))
        if code == 0xda:
            begin = cursor
            while True:
                if data[cursor] != 255:
                    cursor += 1
                    continue
                end = cursor + 1
                while data[end] == 255:
                    end += 1
                if data[end] == 0 or 0xd0 <= data[end] <= 0xd7:
                    cursor = end + 1
                    continue
                records.append((None, data[begin:cursor]))
                break
    raise AssertionError('Missing EOI in test fixture')


def independent_coding(data):
    return b''.join(raw for code, raw in independent_parts(data)
                    if code is None or not (0xe0 <= code <= 0xef or code == 0xfe))


def decoded(data):
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def private_exif(orientation=1):
    """Valid nested EXIF, GPS, next-IFD thumbnail and private strings."""
    def entry(tag, kind, count, value):
        return struct.pack('<HHII', tag, kind, count, value)

    exif_offset = 50
    gps_offset = 80
    thumbnail_offset = 98
    strings_offset = 128
    date = b'2030:01:02 03:04:05\0'
    private_offset = strings_offset + len(date)
    thumb = b'\xff\xd8' + PRIVATE + b'\xff\xd9'
    thumb_offset = private_offset + len(PRIVATE)
    return (b'Exif\0\0II*\0\x08\0\0\0' + struct.pack('<H', 3)
            + entry(274, 3, 1, orientation)
            + entry(34665, 4, 1, exif_offset)
            + entry(34853, 4, 1, gps_offset)
            + struct.pack('<I', thumbnail_offset)
            + struct.pack('<H', 2)
            + entry(36867, 2, len(date), strings_offset)
            + entry(37500, 7, len(PRIVATE), private_offset)
            + struct.pack('<I', 0)
            + struct.pack('<H', 1)
            + entry(27, 7, len(PRIVATE), private_offset)
            + struct.pack('<I', 0)
            + struct.pack('<H', 2)
            + entry(513, 4, 1, thumb_offset)
            + entry(514, 4, 1, len(thumb))
            + struct.pack('<I', 0) + date + PRIVATE + thumb)


class EditedJPEGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = jpeg()
        cls.progressive = jpeg(progressive=True)

    def preserve(self, source, **kwargs):
        return preserve.build_exports(source, preserve.digest(source), **kwargs)

    def assert_preserved(self, source, master):
        self.assertEqual(independent_coding(source), independent_coding(master))
        self.assertEqual(decoded(source), decoded(master))
        with Image.open(BytesIO(master)) as image:
            self.assertEqual(image.info['icc_profile'], PROFILE)
            exif = image.getexif()
            self.assertEqual(set(exif), {305, 315, 33432})
            self.assertEqual(exif[315], preserve.AUTHOR)
            self.assertEqual(exif[33432], preserve.COPYRIGHT)
            tiff = image.info['exif'][6:]
            order = '<' if tiff[:2] == b'II' else '>'
            offset = struct.unpack_from(order + 'I', tiff, 4)[0]
            count = struct.unpack_from(order + 'H', tiff, offset)[0]
            self.assertEqual(struct.unpack_from(order + 'I', tiff, offset + 2 + 12 * count)[0], 0)
        self.assertNotIn(PRIVATE, master)

    def test_baseline_and_progressive_preserve_real_pixels_icc_and_every_scan(self):
        self.assertGreater(sum(code == 0xda for code, _ in independent_parts(self.progressive)), 1)
        for source in (self.baseline, self.progressive):
            with self.subTest(progressive=source is self.progressive):
                exports, receipt = self.preserve(source, preview=True)
                self.assert_preserved(source, exports['master'])
                self.assertEqual(receipt['source_sha256'], preserve.digest(source))
                self.assertEqual(receipt['master_sha256'], preserve.digest(exports['master']))
                self.assertNotEqual(receipt['source_sha256'], receipt['master_sha256'])
                with Image.open(BytesIO(exports['preview'])) as preview:
                    self.assertEqual(preview.size, (640, 360))
                    self.assertEqual(preview.info['icc_profile'], PROFILE)

    def test_private_metadata_before_and_between_progressive_scans_is_removed(self):
        private = b''.join([
            marker(0xe1, private_exif()),
            marker(0xe1, b'http://ns.adobe.com/xap/1.0/\0' + PRIVATE),
            marker(0xe1, b'http://ns.adobe.com/xmp/extension/\0' + PRIVATE),
            marker(0xed, b'Photoshop 3.0\0' + PRIVATE),
            marker(0xe2, b'MPF\0' + PRIVATE),
            marker(0xef, PRIVATE), marker(0xfe, PRIVATE),
        ])
        records = independent_parts(self.progressive)
        after_scan = next(i for i, (code, _) in enumerate(records) if code is None)
        source = (records[0][1] + private
                  + b''.join(raw for _, raw in records[1:after_scan + 1]) + private
                  + b''.join(raw for _, raw in records[after_scan + 1:]) + PRIVATE)
        exports, receipt = self.preserve(source)
        self.assert_preserved(source, exports['master'])
        self.assertEqual(receipt['removed_metadata_segments'], 14)
        self.assertEqual(receipt['discarded_trailing_bytes'], len(PRIVATE))
        self.assertEqual(preserve.segments(exports['master'])[1], 0)

    def test_thumbnail_bearing_jfif_and_jfxx_are_not_retained(self):
        records = independent_parts(self.baseline)
        plain = next(raw for code, raw in records if code == 0xe0)
        payload = plain[4:]
        thumbnail = payload[:12] + bytes((1, len(PRIVATE) // 3 + 1))
        thumbnail += (PRIVATE + b'\0' * 3)[:3 * thumbnail[12] * thumbnail[13]]
        source = self.baseline.replace(plain, marker(0xe0, thumbnail), 1)
        source = source[:2] + marker(0xe0, b'JFXX\0\x10' + PRIVATE) + source[2:]
        master = self.preserve(source)[0]['master']
        self.assert_preserved(source, master)
        headers = [raw[4:] for code, raw in independent_parts(master) if code == 0xe0]
        self.assertEqual(headers, [payload[:12] + b'\0\0'])

    def test_inter_scan_icc_is_preserved_and_explicitly_used_for_derivatives(self):
        records = independent_parts(self.progressive)
        icc = [raw for code, raw in records if code == 0xe2]
        records = [(code, raw) for code, raw in records if code != 0xe2]
        after_scan = next(i for i, (code, _) in enumerate(records) if code is None)
        source = (b''.join(raw for _, raw in records[:after_scan + 1]) + b''.join(icc)
                  + b''.join(raw for _, raw in records[after_scan + 1:]))
        exports, _ = self.preserve(source, preview=True)
        self.assertEqual(independent_coding(source), independent_coding(exports['master']))
        self.assertEqual(decoded(source), decoded(exports['master']))
        self.assertEqual([raw for code, raw in independent_parts(exports['master']) if code == 0xe2], icc)
        with Image.open(BytesIO(exports['preview'])) as preview:
            self.assertEqual(preview.info['icc_profile'], PROFILE)

    def test_fullhd_derivative_is_genuine_downsampling_of_finished_2048_edit(self):
        source = jpeg(size=(2048, 1152), progressive=True)
        exports, receipt = self.preserve(source, fullhd=True, preview=True)
        self.assert_preserved(source, exports['master'])
        self.assertEqual(receipt['exports']['fullhd']['width'], 1920)
        for name, size in (('fullhd', (1920, 1080)), ('preview', (640, 360))):
            with Image.open(BytesIO(exports[name])) as image:
                image.load()
                self.assertEqual(image.size, size)
                self.assertEqual(image.info['icc_profile'], PROFILE)
                self.assertEqual(set(image.getexif()), {305, 315, 33432})

    def test_exact_fullhd_source_is_not_recompressed(self):
        source = jpeg(size=(1920, 1080))
        exports, _ = self.preserve(source, fullhd=True)
        self.assertEqual(exports['master'], exports['fullhd'])

    def test_small_source_requested_fullhd_fails_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'original.jpg'
            source.write_bytes(self.baseline)
            targets = {'master': root / 'wallpapers/master/control.jpg',
                       'fullhd': root / 'wallpapers/1920x1080/control.jpg'}
            with patch.object(preserve, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'without upscaling'):
                    preserve.write_exports(self.baseline, preserve.digest(self.baseline), targets,
                                           source_path=source)
            self.assertEqual(source.read_bytes(), self.baseline)
            self.assertFalse((root / 'wallpapers').exists())

    def test_orientation_checksum_and_invalid_dimensions_fail_closed(self):
        for orientation in (2, 6, 8):
            source = self.baseline[:2] + marker(0xe1, private_exif(orientation)) + self.baseline[2:]
            with self.subTest(orientation=orientation), self.assertRaisesRegex(ValueError, 'already be oriented'):
                self.preserve(source)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            preserve.build_exports(self.baseline, '0' * 64)
        for size in ((1280, 721), (3856, 2169)):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'exactly 16:9'):
                self.preserve(jpeg(size=size))

    def test_malformed_markers_frames_exif_and_icc_fail_closed(self):
        records = independent_parts(self.baseline)
        icc = next(raw for code, raw in records if code == 0xe2)
        frame = next(raw for code, raw in records if code == 0xc0)
        broken = {
            'truncated EOI': self.baseline[:-1],
            'missing EOI': self.baseline[:-2],
            'truncated length': self.baseline[:2] + b'\xff\xe1\0',
            'invalid length': self.baseline[:2] + b'\xff\xe1\0\x01' + self.baseline[2:],
            'unsupported coding marker': self.baseline[:2] + marker(0xdc, b'\0\x01') + self.baseline[2:],
            'surplus frame bytes': self.baseline.replace(frame, marker(0xc0, frame[4:] + PRIVATE), 1),
            'malformed EXIF': self.baseline[:2] + marker(0xe1, b'Exif\0\0II') + self.baseline[2:],
            'duplicate ICC': self.baseline.replace(icc, icc + icc, 1),
            'missing ICC': self.baseline.replace(icc, b'', 1),
            'missing ICC chunk': self.baseline.replace(icc, marker(0xe2, b'ICC_PROFILE\0\x01\x02' + PROFILE), 1),
            'zero ICC chunk': self.baseline.replace(icc, marker(0xe2, b'ICC_PROFILE\0\x00\x01' + PROFILE), 1),
            'unreviewed ICC with private trailer': self.baseline.replace(icc, marker(0xe2, b'ICC_PROFILE\0\x01\x01' + PROFILE + PRIVATE), 1),
            'unsupported Adobe payload': self.baseline[:2] + marker(0xee, b'Adobe' + PRIVATE) + self.baseline[2:],
        }
        for case, source in broken.items():
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.preserve(source)

    def test_split_icc_chunks_are_retained_byte_for_byte(self):
        records = independent_parts(self.baseline)
        original = next(raw for code, raw in records if code == 0xe2)
        chunks = (marker(0xe2, b'ICC_PROFILE\0\x02\x02' + PROFILE[300:])
                  + marker(0xe2, b'ICC_PROFILE\0\x01\x02' + PROFILE[:300]))
        source = self.baseline.replace(original, chunks, 1)
        master = self.preserve(source)[0]['master']
        self.assert_preserved(source, master)
        self.assertIn(chunks, master)

    def test_source_output_symlinks_and_paths_outside_export_directories_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'wallpapers/master/original.jpg'
            original.parent.mkdir(parents=True)
            original.write_bytes(self.baseline)
            symlink = original.parent / 'link.jpg'
            symlink.symlink_to(original)
            controls = [({'master': original}, original),
                        ({'master': root / 'escaped.jpg'}, None),
                        ({'master': symlink}, None)]
            for targets, source in controls:
                with self.subTest(targets=targets), patch.object(preserve, 'ROOT', root):
                    with self.assertRaises(ValueError):
                        preserve.write_exports(self.baseline, preserve.digest(self.baseline), targets,
                                               source_path=source)
            self.assertEqual(original.read_bytes(), self.baseline)
            self.assertEqual(set(original.parent.iterdir()), {original, symlink})

    def test_symlinked_export_parent_cannot_redirect_writes_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / 'repository'
            outside = parent / 'outside'
            outside.mkdir()
            (root / 'wallpapers').mkdir(parents=True)
            (root / 'wallpapers/master').symlink_to(outside, target_is_directory=True)
            with patch.object(preserve, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'repository output directories'):
                    preserve.write_exports(self.baseline, preserve.digest(self.baseline),
                                           {'master': root / 'wallpapers/master/control.jpg'})
            self.assertEqual(list(outside.iterdir()), [])

    def test_renderer_explicit_mode_preserves_edit_and_never_enters_grading_path(self):
        for size in ((2048, 1152), (1280, 720)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs = root / 'inputs'
                inputs.mkdir()
                original = inputs / 'finished.jpg'
                data = jpeg(size=size)
                original.write_bytes(data)
                recipe = {'slug': 'finished-edit', 'title': 'Finished edit', 'theme': 'ember',
                          'description': 'Test fixture', 'processing': preserve.MODE,
                          'source': {'collection': 'pictures', 'file': original.name,
                                     'sha256': preserve.digest(data), 'width': size[0], 'height': size[1]},
                          'crop_px': [0, 0, *size], 'adjustments': {}, 'based_on_existing_edit': True}
                (root / 'metadata').mkdir()
                (root / 'metadata/recipes.json').write_text(json.dumps({'wallpapers': [recipe]}))
                argv = ['render_wallpapers.py', '--pictures-root', str(inputs), '--ventoy-root', str(inputs)]
                with (patch.object(preserve, 'ROOT', root), patch.object(renderer, 'ROOT', root),
                      patch.object(sys, 'argv', argv),
                      patch.object(renderer, 'grade', side_effect=AssertionError('Regrading forbidden')),
                      patch.object(renderer, 'load_srgb', side_effect=AssertionError('Conversion forbidden')),
                      patch.object(renderer, 'export_jpeg', side_effect=AssertionError('Master recompression forbidden'))):
                    if size[0] < 1920:
                        with self.assertRaisesRegex(SystemExit, 'without upscaling'):
                            renderer.main()
                        self.assertFalse((root / 'wallpapers').exists())
                        self.assertFalse((root / 'metadata/collection.json').exists())
                    else:
                        renderer.main()
                        master = (root / 'wallpapers/master/finished-edit.jpg').read_bytes()
                        self.assert_preserved(data, master)
                        collection = json.loads((root / 'metadata/collection.json').read_text())
                        self.assertEqual(collection['wallpapers'][0]['source']['sha256'], preserve.digest(data))
                        self.assertEqual(collection['wallpapers'][0]['sha256'], preserve.digest(master))
                self.assertEqual(original.read_bytes(), data)

    def test_clean_reviewed_gimp_attribution_preserves_the_entire_file_idempotently(self):
        source = jpeg(size=(2048, 1152), progressive=True,
                      exif=preserve.attribution('GIMP 3.0.4; local photographic editing'))
        master, receipt = self.preserve(source)[0]['master'], self.preserve(source)[1]
        self.assertEqual(master, source)
        self.assertTrue(receipt['master_bytes_preserved'])
        self.assertTrue(receipt['existing_attribution_preserved'])
        self.assertEqual(self.preserve(master)[0]['master'], source)
        self.assert_preserved(source, master)

    def test_invisible_private_exif_bytes_cannot_enter_existing_attribution_fast_path(self):
        source = jpeg(exif=preserve.attribution('GIMP 3.0.4; local photographic editing'))
        exif = next(raw for code, raw in independent_parts(source) if code == 0xe1)
        payload = exif[4:]
        padding = bytearray(payload)
        padding[6 + 89] = ord('P')  # Unused alignment byte; getexif values still match.
        private_payloads = {
            'unreferenced trailer': payload + PRIVATE,
            'nonzero padding': bytes(padding),
            'unreviewed software': preserve.attribution(PRIVATE.decode('ascii')),
        }
        for case, replacement in private_payloads.items():
            with self.subTest(case=case):
                mutant = source.replace(exif, marker(0xe1, replacement), 1)
                exports, receipt = self.preserve(mutant)
                self.assertFalse(receipt['existing_attribution_preserved'])
                self.assertFalse(receipt['master_bytes_preserved'])
                self.assert_preserved(mutant, exports['master'])
        duplicated = source.replace(exif, exif + exif, 1)
        self.assertFalse(self.preserve(duplicated)[1]['existing_attribution_preserved'])

    def test_published_edited_master_recovery_never_rewrites_source_file(self):
        source = jpeg(size=(2048, 1152), progressive=True,
                      exif=preserve.attribution('GIMP 3.0.4; local photographic editing'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            master = root / 'wallpapers/master/finished-edit.jpg'
            master.parent.mkdir(parents=True)
            master.write_bytes(source)
            before = master.stat()
            recipe = {'slug': 'finished-edit', 'title': 'Finished edit', 'theme': 'ember',
                      'description': 'Test fixture', 'processing': preserve.MODE,
                      'source': {'collection': 'edited', 'file': master.name,
                                 'sha256': preserve.digest(source), 'width': 2048, 'height': 1152},
                      'crop_px': [0, 0, 2048, 1152], 'adjustments': {}, 'based_on_existing_edit': True,
                      'featured': True}
            (root / 'metadata').mkdir()
            (root / 'metadata/recipes.json').write_text(json.dumps({'wallpapers': [recipe]}))
            argv = ['render_wallpapers.py', '--pictures-root', 'unused', '--ventoy-root', 'unused']
            with patch.object(preserve, 'ROOT', root), patch.object(renderer, 'ROOT', root), patch.object(sys, 'argv', argv):
                renderer.main()
            self.assertEqual(master.read_bytes(), source)
            self.assertEqual(master.stat().st_ino, before.st_ino)
            self.assertEqual(master.stat().st_mtime_ns, before.st_mtime_ns)
            for directory, size in (('wallpapers/1920x1080', (1920, 1080)), ('previews', (640, 360))):
                with Image.open(root / directory / master.name) as image:
                    self.assertEqual(image.size, size)
            collection = json.loads((root / 'metadata/collection.json').read_text())
            self.assertEqual(collection['wallpapers'][0]['source']['sha256'], preserve.digest(source))
            self.assertEqual(collection['wallpapers'][0]['sha256'], preserve.digest(source))
            self.assertTrue(collection['wallpapers'][0]['featured'])

    def test_collection_accepts_real_progressive_edit_flags_with_strict_metadata(self):
        source = jpeg(size=(2048, 1152), progressive=True,
                      exif=preserve.attribution('GIMP 3.0.4; local photographic editing'))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'published.jpg'
            path.write_bytes(source)
            verifier.check_image(path, (2048, 1152), (2048, 1152), PROFILE, preserve_edit=True)

    def test_collection_rejects_metadata_that_pillow_does_not_expose(self):
        source = jpeg(progressive=True, exif=preserve.attribution('GIMP 3.0.4; local photographic editing'))
        original_exif = next(raw for code, raw in independent_parts(source) if code == 0xe1)
        mutants = {'unknown APP15': source[:2] + marker(0xef, PRIVATE) + source[2:],
                   'bytes after EOI': source + PRIVATE,
                   'unreferenced EXIF bytes': source.replace(original_exif, marker(0xe1, original_exif[4:] + PRIVATE), 1)}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'published.jpg'
            for case, data in mutants.items():
                path.write_bytes(data)
                with self.subTest(case=case), self.assertRaisesRegex(ValueError, 'strict published allowlist'):
                    verifier.check_image(path, (1280, 720), (1280, 720), PROFILE, preserve_edit=True)


if __name__ == '__main__':
    unittest.main()
