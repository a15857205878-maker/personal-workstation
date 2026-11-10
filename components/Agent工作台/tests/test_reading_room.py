import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from reading_room import ReadingRoom

class ReadingRoomTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=ReadingRoom(self.root/'data')
 def tearDown(self):self.temp.cleanup()
 def add(self):
  p=self.root/'测试.md';p.write_text('# 你好\n\n这是正文。',encoding='utf-8');return p,self.store.import_paths([p])['items'][0]['id']
 def test_copy_dedup_read_progress_and_restart(self):
  p,i=self.add();original=p.read_bytes();self.assertEqual(len(self.store.import_paths([p])['items']),1)
  self.assertIn('你好',self.store.read(i)['text']);self.store.update({'id':i,'position':.4,'state':'reading','bookmark':True,'notes':'笔记'})
  again=ReadingRoom(self.root/'data');item=again.read(i)['item'];self.assertEqual(item['position'],.4);self.assertEqual(len(item['bookmarks']),1);self.assertEqual(p.read_bytes(),original)
  again.update({'id':i,'archive':True});self.assertEqual(again.listing()['items'],[]);self.assertTrue(p.exists());self.assertTrue((again.root/(i+'.md')).exists())
  self.assertEqual(len(again.listing()['archived']),1);again.update({'id':i,'archive':False});self.assertEqual(again.read(i)['item']['notes'],'笔记')
 def test_invalid_ids_paths_pdf_and_update_are_rejected(self):
  _,i=self.add()
  for p in [{'id':'../x'},{'id':i,'path':'secret'},{'id':i,'position':float('nan')},{'id':i,'page':False},{'id':i,'state':'bad'}]:
   with self.assertRaises(ValueError):self.store.update(p)
  bad=self.root/'bad.pdf';bad.write_text('not a pdf');self.assertEqual(len(self.store.import_paths([bad])['errors']),1)
  with self.assertRaises(ValueError):self.store.read('../../secret')
 def test_corruption_preserves_index_and_never_replaces_it(self):
  p,_=self.add();self.store.index.write_text('broken',encoding='utf-8')
  with self.assertRaises(ValueError):self.store.import_paths([p])
  self.assertEqual(self.store.index.read_text(),'broken')
 def test_structurally_invalid_metadata_is_preserved(self):
  _,i=self.add();value=self.store._load();value['items'][0]['notes']={'bad':'value'};raw=json.dumps(value);self.store.index.write_text(raw,encoding='utf-8')
  with self.assertRaises(ValueError):self.store.listing()
  self.assertEqual(self.store.index.read_text(),raw)
 def test_pdf_copy_and_page_bookmark(self):
  p=self.root/'阅读.pdf';p.write_bytes(b'%PDF-1.4\nfixture')
  i=self.store.import_paths([p])['items'][0]['id'];self.assertIn('base64',self.store.read(i));self.store.update({'id':i,'page':12,'bookmark':True});self.assertEqual(self.store.read(i)['item']['bookmarks'][0]['page'],12)
 def test_metadata_size_guard_preserves_previous_index(self):
  _,i=self.add();before=self.store.index.read_bytes()
  with patch('reading_room.MAX_INDEX_BYTES',len(before)+10):
   with self.assertRaises(ValueError):self.store.update({'id':i,'notes':'笔记'*500})
  self.assertEqual(self.store.index.read_bytes(),before)
 def test_many_legal_notes_remain_readable_beyond_old_four_mib_limit(self):
  _,i=self.add();value=self.store._load();base=value['items'][0]
  value['items']=[{**base,'id':format(n,'032x'),'notes':'读'*8000} for n in range(200)]
  self.store._save(value);self.assertGreater(self.store.index.stat().st_size,4*1024*1024);self.assertEqual(len(self.store.listing()['items']),200)
if __name__=='__main__':unittest.main()
