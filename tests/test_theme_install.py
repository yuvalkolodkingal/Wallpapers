"""Safety checks for installing into existing user directories, no live changes."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/theme.py'

class ThemeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wallpaper-install-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.destination = self.directory / 'Folder with spaces'

    def run_install(self, theme='all', target='omarchy', *extra):
        return subprocess.run([sys.executable, str(SCRIPT), 'install', theme,
                               '--target', target, '--dest', str(self.destination), *extra],
                              capture_output=True, text=True)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dry_runs_create_nothing(self):
        for target in ('omarchy', 'hyprland', 'wallpapers'):
            self.assert_success(self.run_install('all', target, '--dry-run'))
            self.assertFalse(self.destination.exists())

    def test_themes_copy_backgrounds_and_are_idempotent(self):
        self.assert_success(self.run_install())
        photos = list(self.destination.glob('*/backgrounds/*.jpg'))
        self.assertEqual(len(photos), 18)
        self.assertTrue(all(not p.is_symlink() for p in photos))
        self.assertEqual(len(list(self.destination.glob('*/hyprland.lua'))), 4)
        self.assertFalse(list(self.destination.glob('*/hyprland.conf')))
        before = {str(p): p.stat().st_mtime_ns for p in self.destination.rglob('*') if p.is_file()}
        self.assert_success(self.run_install())
        self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in self.destination.rglob('*') if p.is_file()})

    def test_plain_hyprland_has_both_config_formats(self):
        self.assert_success(self.run_install('canopy', 'hyprland'))
        self.assertTrue((self.destination/'ykg-canopy/hyprland.lua').is_file())
        self.assertTrue((self.destination/'ykg-canopy/hyprland.conf').is_file())
        self.assertEqual(len(list(self.destination.iterdir())), 1)

    def test_modified_theme_prevents_all_new_installations(self):
        self.assert_success(self.run_install('lagoon'))
        custom = self.destination/'ykg-lagoon/colors.toml'
        custom.write_text('user changes\n')
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(custom.read_text(), 'user changes\n')
        self.assertEqual([p.name for p in self.destination.iterdir()], ['ykg-lagoon'])

    def test_wallpapers_merge_themes_and_sizes(self):
        self.assert_success(self.run_install('ember', 'wallpapers'))
        self.assertEqual(len(list((self.destination/'1920x1080').glob('*.jpg'))), 2)
        self.assert_success(self.run_install('all', 'wallpapers'))
        self.assertEqual(len(list((self.destination/'1920x1080').glob('*.jpg'))), 18)
        self.assert_success(self.run_install('ember', 'wallpapers', '--resolution', 'master'))
        self.assertEqual(len(list((self.destination/'master').glob('*.jpg'))), 2)
        self.assert_success(self.run_install('all', 'wallpapers'))
        self.assertEqual((self.destination/'COPYRIGHT').read_bytes(), (ROOT/'COPYRIGHT').read_bytes())

    def test_wallpaper_conflict_preflights_before_copying(self):
        folder = self.destination/'1920x1080'
        folder.mkdir(parents=True)
        custom = folder/'rose-city.jpg'
        custom.write_text('personal image')
        result = self.run_install('all', 'wallpapers')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(folder.iterdir()), [custom])
        self.assertFalse((self.destination/'COPYRIGHT').exists())
        self.assertEqual(custom.read_text(), 'personal image')

    def test_wallpaper_symlink_is_not_followed(self):
        outside = self.directory/'outside'
        outside.mkdir()
        self.destination.mkdir()
        (self.destination/'1920x1080').symlink_to(outside, target_is_directory=True)
        result = self.run_install('all', 'wallpapers')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.destination/'COPYRIGHT').exists())

if __name__ == '__main__':
    unittest.main()
