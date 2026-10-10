"""Uploaded photos remain source-sized through export, gallery and installation."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_gallery as gallery
import render_wallpapers as renderer
import theme
import verify_collection as verifier


class NativeUploadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='wallpaper-native-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'repository'
        self.uploads = Path(temporary.name) / 'uploads'
        self.uploads.mkdir()
        (self.root / 'metadata').mkdir(parents=True)
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles/sRGB.icc').write_bytes(renderer.ICC)
        (self.root / 'COPYRIGHT').write_text('Photography by Yuval Kolodkin-Gal.\n')
        self.recipes = []
        self.originals = {}
        for slug, size, crop in [('small-photo', (1280, 960), [0, 120, 1280, 840]),
                                 ('large-photo', (2048, 1152), [0, 0, 2048, 1152])]:
            path = self.uploads / f'{slug}.jpg'
            image = Image.new('RGB', size, '#4a7465')
            exif = Image.Exif()
            exif[271] = 'Private device model'
            image.save(path, exif=exif)
            self.originals[path] = path.read_bytes()
            self.recipes.append({
                'slug': slug, 'title': slug.replace('-', ' ').title(), 'theme': 'canopy',
                'description': 'A photographic test fixture.',
                'source': {'collection': 'uploads', 'file': path.name,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                           'width': size[0], 'height': size[1]},
                'crop_px': crop, 'adjustments': {'contrast': 0.1},
                'based_on_existing_edit': False,
            })
        self.write_recipes()
        backgrounds = self.root / 'themes/canopy/backgrounds'
        backgrounds.mkdir(parents=True)
        (backgrounds.parent / 'colors.toml').write_text(
            'background = "#111111"\nforeground = "#eeeeee"\naccent = "#558855"\nmuted = "#888888"\n')
        (backgrounds.parent / 'hyprland.lua').write_text('-- Fixture\n')
        self.argv = ['render_wallpapers.py', '--pictures-root', 'unused',
                     '--ventoy-root', 'unused', '--uploads-root', str(self.uploads)]

    def write_recipes(self):
        (self.root / 'metadata/recipes.json').write_text(json.dumps({
            'author': renderer.AUTHOR, 'wallpapers': self.recipes,
        }))

    def render(self):
        with patch.object(renderer, 'ROOT', self.root), patch.object(sys, 'argv', self.argv):
            with redirect_stdout(StringIO()):
                renderer.main()
        collection = json.loads((self.root / 'metadata/collection.json').read_text())
        for photo in collection['wallpapers']:
            target = photo['fullhd'] or photo['master']
            link = self.root / 'themes/canopy/backgrounds' / f'{photo["slug"]}.jpg'
            if not link.is_symlink():
                link.symlink_to('../../../' + target)
        return collection

    def verify(self):
        output = StringIO()
        with patch.object(verifier, 'ROOT', self.root), redirect_stderr(output), redirect_stdout(output):
            result = verifier.main()
        return result, output.getvalue()

    def test_mixed_sizes_keep_native_pixels_and_install_all_photos(self):
        collection = self.render()
        small, large = collection['wallpapers']
        self.assertIsNone(small['fullhd'])
        self.assertEqual((small['width'], small['height']), (1280, 720))
        self.assertEqual(large['fullhd'], 'wallpapers/1920x1080/large-photo.jpg')
        self.assertFalse((self.root / 'wallpapers/1920x1080/small-photo.jpg').exists())
        for photo in (small, large):
            with Image.open(self.root / photo['master']) as image:
                self.assertEqual(set(image.getexif()), {305, 315, 33432})
                self.assertEqual(image.size, (photo['width'], photo['height']))
            with Image.open(self.root / photo['preview']) as image:
                self.assertEqual(image.size, (640, 360))
        result, output = self.verify()
        self.assertEqual(result, 0, output)
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)

        destination = self.root.parent / 'installed'
        with patch.object(theme, 'ROOT', self.root), redirect_stdout(StringIO()):
            theme.install_wallpapers(['canopy'], destination, False, '1920x1080')
            theme.install_wallpapers(['canopy'], destination, False, '1920x1080')
            files = theme.files_for('canopy')
        self.assertEqual((destination / 'native/small-photo.jpg').read_bytes(),
                         (self.root / small['master']).read_bytes())
        self.assertTrue((destination / '1920x1080/large-photo.jpg').is_file())
        self.assertFalse((destination / '1920x1080/small-photo.jpg').exists())
        self.assertEqual(files[Path('backgrounds/small-photo.jpg')], self.root / small['master'])

    def test_gallery_has_native_downloads_without_false_fullhd_link(self):
        self.render()
        page = gallery.build(self.root)
        small = page.split('<article class="photo" id="small-photo"', 1)[1].split('</article>', 1)[0]
        large = page.split('<article class="photo" id="large-photo"', 1)[1].split('</article>', 1)[0]
        self.assertIn('href="wallpapers/master/small-photo.jpg"', small)
        self.assertIn('1280 × 720', small)
        self.assertNotIn('data-fullhd', small)
        self.assertIn('data-fullhd', large)
        self.assertNotIn('href="None"', page)

    def test_verifier_rejects_upscaled_claim_and_untracked_derivative(self):
        collection = self.render()
        collection['wallpapers'][0]['fullhd'] = 'wallpapers/1920x1080/small-photo.jpg'
        path = self.root / 'metadata/collection.json'
        path.write_text(json.dumps(collection))
        result, output = self.verify()
        self.assertEqual(result, 1)
        self.assertIn('must not advertise a Full HD export', output)
        collection['wallpapers'][0]['fullhd'] = None
        path.write_text(json.dumps(collection))
        (self.root / 'wallpapers/1920x1080/small-photo.jpg').write_bytes(
            (self.root / 'wallpapers/1920x1080/large-photo.jpg').read_bytes())
        result, output = self.verify()
        self.assertEqual(result, 1)
        self.assertIn('Export file set differs', output)

    def test_changed_upload_hash_or_dimensions_fail_before_export(self):
        for mismatch in ('sha256', 'width'):
            with self.subTest(mismatch=mismatch):
                saved = self.recipes[0]['source'][mismatch]
                self.recipes[0]['source'][mismatch] = '0' * 64 if mismatch == 'sha256' else 1279
                self.write_recipes()
                with self.assertRaises(SystemExit):
                    self.render()
                self.assertFalse((self.root / 'wallpapers').exists())
                self.recipes[0]['source'][mismatch] = saved


if __name__ == '__main__':
    unittest.main()
