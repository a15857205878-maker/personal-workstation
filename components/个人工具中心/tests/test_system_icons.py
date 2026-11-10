"""System desktop entries must appear alongside ordinary software links."""
import tempfile, unittest
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from shortcut_model import ShortcutService, ShortcutBackend


class SystemIconScanTests(unittest.TestCase):
    def test_scan_includes_system_entries_without_lnk_files(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = ShortcutBackend(folder)
            items = [dict(path='system:'+key, name=name, kind='system', icon='')
                     for key, name in [('computer','此电脑'), ('recycle','回收站'), ('control','控制面板')]]
            with patch.object(backend, 'desktop_dirs', return_value=[Path(folder)]), \
                 patch.object(backend, 'system_items', return_value=items, create=True):
                found = ShortcutService(folder, backend).scan()
            self.assertEqual({item.get('name') for item in found}, {'此电脑','回收站','控制面板'})


if __name__ == '__main__': unittest.main()


class FakeSystemBackend:
    def __init__(self):
        self.values = {'': None, 'empty': ['old-empty.ico,0', 2], 'full': ['old-full.ico,0', 1]}
        self.fail_once = False
    def read(self, key):
        return dict(values=deepcopy(self.values), icon='old-default.ico,0')
    def write(self, key, values):
        if self.fail_once:
            self.fail_once = False
            self.values[''] = deepcopy(values[''])
            raise PermissionError('模拟部分写入失败')
        self.values = deepcopy(values)


class SystemIconMutationTests(unittest.TestCase):
    def setUp(self):
        from system_icons import SystemIconService
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.backend = FakeSystemBackend()
        self.shortcuts = ShortcutService(self.base, backend=object(), asset_root=self.base/'cache')
        self.service = SystemIconService(self.shortcuts, self.backend)
        self.path = 'system:recycle'
        self.original = self.backend.read('recycle')
        self.icon = self.base/'partner.ico'
        self.icon.write_bytes(b'\0\0\1\0\1\0test')
    def test_recycle_changes_both_states_and_restore_preserves_missing_default(self):
        self.service.apply(self.path, self.icon, dict(system_state=self.original))
        values = self.backend.read('recycle')['values']
        self.assertEqual(values['empty'], values['full'])
        self.assertEqual(values[''], values['full'])
        self.assertTrue(Path(values[''][0].rsplit(',',1)[0]).is_file())
        # A second apply must still restore the first original snapshot.
        self.service.apply(self.path, self.icon, dict(system_state=self.backend.read('recycle')))
        self.service.restore(self.path)
        self.assertEqual(self.backend.read('recycle'), self.original)
    def test_stale_preview_and_external_changes_are_not_overwritten(self):
        self.backend.values['full'] = ['external.ico,0', 1]
        with self.assertRaises(ValueError):
            self.service.apply(self.path, self.icon, dict(system_state=self.original))
        self.backend.values = deepcopy(self.original['values'])
        self.service.apply(self.path, self.icon, dict(system_state=self.original))
        self.backend.values['full'] = ['external.ico,0', 1]
        with self.assertRaises(ValueError): self.service.restore(self.path)
        self.assertEqual(self.backend.values['full'], ['external.ico,0', 1])
    def test_partial_write_failure_rolls_back(self):
        self.backend.fail_once = True
        with self.assertRaises(PermissionError):
            self.service.apply(self.path, self.icon, dict(system_state=self.original))
        self.assertEqual(self.backend.read('recycle'), self.original)
    def test_unknown_system_target_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.apply('system:arbitrary', self.icon, dict(system_state=self.original))


@unittest.skipUnless(os.name == 'nt', 'Windows Shell required')
class SystemIconWindowsTests(unittest.TestCase):
    def test_namespace_entries_have_real_preview_images(self):
        from system_icons import SYSTEM_ICONS
        from win_icons import shortcut_image
        for key, (name, guid) in SYSTEM_ICONS.items():
            with self.subTest(name=name):
                image = shortcut_image(dict(path='system:'+key, shell_path='::'+guid, icon=''), 72)
                self.assertIsNotNone(image)
                self.assertIsNotNone(image.getbbox())
