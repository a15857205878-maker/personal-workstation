import unittest,tempfile,json
from pathlib import Path
from reading_room import ReadingRoom

class LeisureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.r=ReadingRoom(self.root/'data')
 def book(self):
  p=self.root/'读物.md';p.write_text('# 原件\n正文',encoding='utf-8');return self.r.import_paths([p])['items'][0]
 def test_preferences_persist_and_summary_is_read_only(self):
  b=self.book();self.r.preferences_save(dict(font=22,paper='dark',volume=0,last_book_id=b['id']))
  again=ReadingRoom(self.root/'data');self.assertEqual(again.preferences()['volume'],0);self.assertEqual(again.preferences()['font'],22)
  before={str(p):p.read_bytes() for p in self.r.root.iterdir()};v=again.overview();self.assertEqual(v['resume']['id'],b['id']);self.assertEqual(v['counts']['books'],1);self.assertEqual(before,{str(p):p.read_bytes() for p in self.r.root.iterdir()})
 def test_invalid_preferences_preserve_file(self):
  b=self.book();self.r.preferences_save(dict(last_book_id=b['id']));p=self.r.root/'preferences.json';before=p.read_bytes()
  for data in (dict(font=True),dict(font=99),dict(volume=float('nan')),dict(paper='green'),dict(last_book_id='../x'),dict(path='x')):
   with self.assertRaises(ValueError):self.r.preferences_save(data)
  self.assertEqual(p.read_bytes(),before)
 def test_archive_keeps_original_and_no_resume_until_restored(self):
  b=self.book();self.r.preferences_save(dict(last_book_id=b['id']));self.r.update(dict(id=b['id'],archive=True));self.assertIsNone(self.r.overview()['resume']);self.assertTrue((self.root/'读物.md').exists());self.r.update(dict(id=b['id'],archive=False));self.assertEqual(self.r.overview()['resume']['id'],b['id'])
 def test_remove_exact_bookmark_preserves_others(self):
  b=self.book();self.r.update(dict(id=b['id'],position=.2,bookmark=True));self.r.update(dict(id=b['id'],position=.7,bookmark=True))
  self.r.update(dict(id=b['id'],remove_bookmark=dict(position=.2,page=1)));marks=self.r.read(b['id'])['item']['bookmarks'];self.assertEqual(marks,[dict(position=.7,page=1)])
  with self.assertRaises(ValueError):self.r.update(dict(id=b['id'],remove_bookmark=dict(position=True,page=1)))
 def test_summary_does_not_initialize_tools_or_models(self):
  from backend import Bridge
  b=Bridge(self.root/'missing',data_dir=self.root/'data')
  try:
   r=b.call('workstation_leisure_status',{});self.assertTrue(r['ok'],r);self.assertIsNone(b._auto);self.assertIsNone(b._station)
   self.assertFalse(b.call('workstation_leisure_status',{'path':'anything'})['ok'])
  finally:b.close_station()

if __name__=='__main__':unittest.main()
