import unittest
from unittest.mock import Mock
from desktop_chrome import WindowControls
class TrayActions(unittest.TestCase):
 def test_tray_hide_and_restore_preserve_window(self):
  w=Mock(); c=WindowControls(w); c.tray=Mock()
  c.action({'action':'tray'}); c.tray.hide.assert_called_once(); w.destroy.assert_not_called()
 def test_failed_tray_does_not_hide_window(self):
  w=Mock(); c=WindowControls(w); c.tray=Mock(); c.tray.hide.side_effect=RuntimeError('tray unavailable')
  with self.assertRaisesRegex(RuntimeError,'tray unavailable'):c.action({'action':'tray'})
  w.hide.assert_not_called(); w.destroy.assert_not_called()
 def test_tray_requires_installed_service(self):
  w=Mock(); c=WindowControls(w)
  with self.assertRaisesRegex(RuntimeError,'托盘'):c.action({'action':'tray'})
  w.hide.assert_not_called()
if __name__=='__main__': unittest.main()
