import unittest,tempfile
from pathlib import Path
from reading_room import ReadingRoom

class ReadingExportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.r=ReadingRoom(self.root/'data')
 def test_export_contains_only_notes_and_bookmarks_and_does_not_write(self):
  p=self.root/'读物.md';p.write_text('PRIVATE_BOOK_BODY',encoding='utf-8');i=self.r.import_paths([p])['items'][0]['id'];self.r.update(dict(id=i,position=.3,bookmark=True,notes='我的重点笔记'))
  before={str(p):p.read_bytes() for p in self.r.root.iterdir()};v=self.r.export_notes(i)
  self.assertIn('我的重点笔记',v['text']);self.assertIn('30%',v['text']);self.assertNotIn('PRIVATE_BOOK_BODY',v['text']);self.assertNotIn(str(self.root),v['text']);self.assertTrue(v['filename'].endswith('.md'));self.assertEqual(before,{str(p):p.read_bytes() for p in self.r.root.iterdir()})
 def test_invalid_id_and_audio_are_rejected(self):
  p=self.root/'audio.wav';p.write_bytes(b'fixture');i=self.r.import_paths([p],kind='audio')['items'][0]['id']
  for identifier in ('../secret',i):
   with self.assertRaises(ValueError):self.r.export_notes(identifier)

if __name__=='__main__':unittest.main()
