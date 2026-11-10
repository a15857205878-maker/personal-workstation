from pathlib import Path
import tempfile,unittest,time,json,os
from pc_files import ComputerFiles
class ComputerFilesTests(unittest.TestCase):
 def test_switching_library_hides_old_folder_and_invalidates_old_download_ticket(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'work') as directory:
   root=Path(directory);one=root/'one';two=root/'two';one.mkdir();two.mkdir()
   (one/'old.txt').write_text('old');(two/'new.txt').write_text('new')
   files=ComputerFiles(root/'config');files.set_library(one)
   ticket=files.library_files()['files'][0]['id'];files.set_library(two)
   self.assertEqual([r['name'] for r in files.library_files()['files']],['new.txt'])
   with self.assertRaises(ValueError):files.open_file(ticket)
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'work');self.root=Path(self.temp.name);self.files=self.root/'files';self.files.mkdir();self.s=ComputerFiles(self.root/'service')
 def tearDown(self):self.temp.cleanup()
 def test_default_empty_and_local_registration_then_search_download(self):
  (self.files/'预算2026.xlsx').write_bytes(b'original');self.assertEqual(self.s.search('预算')['roots'],[]);self.s.add_root(self.files)
  result=self.s.search('预算');self.assertEqual(len(result['files']),1);self.assertNotIn(str(self.root),json.dumps(result));row=result['files'][0]
  with self.s.open_file(row['id']) as stream:self.assertEqual(stream.read(),b'original')
 def test_private_files_and_links_are_not_returned(self):
  (self.files/'pairing.json').write_text('secret');(self.files/'.env').write_text('secret');(self.files/'doc.txt').write_text('ok');private=self.files/'.ssh';private.mkdir();(private/'doc.txt').write_text('private');self.s.add_root(self.files)
  self.assertEqual([r['name'] for r in self.s.search('doc')['files']],['doc.txt']);self.assertEqual(self.s.search('pairing')['files'],[])
 def test_changed_removed_roots_and_expired_tickets_are_rejected(self):
  p=self.files/'doc.txt';p.write_text('first');root=self.s.add_root(self.files)['roots'][0];ticket=self.s.search('doc')['files'][0]['id'];p.write_text('changed')
  with self.assertRaises(ValueError):self.s.open_file(ticket)
  ticket=self.s.search('doc')['files'][0]['id'];self.s.remove_root(root['id'])
  with self.assertRaises(ValueError):self.s.open_file(ticket)
 def test_traversal_empty_and_too_broad_roots_are_rejected(self):
  for query in ['', '../doc','C:/private/doc','x'*121]:
   with self.assertRaises(ValueError):self.s.search(query)
  with self.assertRaises(ValueError):self.s.add_root(Path(self.files.anchor))
  with self.assertRaises(ValueError):self.s.open_file('../secret')
 def test_fixed_library_lists_without_keywords_and_does_not_include_other_roots(self):
  other=self.root/'other';other.mkdir();(other/'private.txt').write_text('outside library');self.s.add_root(other)
  self.assertEqual(self.s.library_files()['files'],[])
  (self.files/'预算.txt').write_text('library original');self.s.set_library(self.files)
  result=self.s.library_files();self.assertEqual([r['name'] for r in result['files']],['预算.txt']);self.assertEqual([r['name'] for r in self.s.library_files('预算')['files']],['预算.txt'])
  with self.s.open_file(result['files'][0]['id']) as stream:self.assertEqual(stream.read(),b'library original')
  self.s.remove_root(result['roots'][0]['id']);self.assertEqual(self.s.library_files()['files'],[])
 def test_search_parallelism_is_bounded(self):
  self.s._search_slots.acquire();self.s._search_slots.acquire()
  try:
   with self.assertRaises(ValueError):self.s.search('doc')
  finally:self.s._search_slots.release();self.s._search_slots.release()
 def test_hardlinks_are_not_shared(self):
  outside=self.root/'outside.txt';outside.write_text('private');os.link(outside,self.files/'doc.txt');self.s.add_root(self.files);self.assertEqual(self.s.search('doc')['files'],[])
 def test_ticket_expiry(self):
  (self.files/'doc.txt').write_text('ok');self.s.add_root(self.files);ticket=self.s.search('doc')['files'][0]['id'];self.s.ttl=0
  with self.assertRaises(ValueError):self.s.open_file(ticket)
 def test_result_limit_is_explicit_and_config_is_not_remote_supplied(self):
  for i in range(60):(self.files/f'doc{i}.txt').write_text(str(i))
  self.s.add_root(self.files);result=self.s.search('doc');self.assertEqual(len(result['files']),50);self.assertTrue(result['limited']);self.assertEqual(len(self.s.local_roots()['roots']),1)
if __name__=='__main__':unittest.main()
