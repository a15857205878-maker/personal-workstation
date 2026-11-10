import unittest,tempfile,sys,hashlib,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_workbench import fixture,message
from room_store import RoomStore
from runner import RoomRunner

class RealRunnerTests(unittest.TestCase):
    def test_real_isolated_next_card_bake_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=fixture(Path(temporary));store=RoomStore(root);runner=RoomRunner(root)
            original_rules={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'PROTOCOL.md',root/'persona/conductor.md',root/'room/brief.md')}
            for command in (['next','A'],):self.assertEqual(runner(command)['exit_code'],0)
            message(root,1,'A');self.assertEqual(runner(['next','B'])['exit_code'],0)
            message(root,2,'B');self.assertEqual(runner(['next','SUM'])['exit_code'],0)
            message(root,3,'SUM');self.assertEqual(runner(['bake'])['exit_code'],0)
            log=(root/'room/log.md').read_bytes();self.assertEqual(runner(['bake'])['exit_code'],0);self.assertEqual(log,(root/'room/log.md').read_bytes())
            self.assertEqual(runner(['card','B','-n','2'])['exit_code'],0)
            self.assertIn('请只回一个席位块',store.read_document('card','B.md')['text'])
            check=runner(['--check']);self.assertEqual(check['exit_code'],0,check);self.assertIn('10 passed, 0 failed',check['output'])
            self.assertEqual(len(store.snapshot()['messages']),3)
            for path,digest in original_rules.items():self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),digest)
    def test_runner_timeout_reports_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'bin').mkdir();(root/'bin/room.ps1').write_text('Start-Sleep -Seconds 5',encoding='utf-8')
            result=RoomRunner(root,timeout=.1)(['status'])
            self.assertNotEqual(result['exit_code'],0);self.assertIn('超时',result['output'])
    def test_runner_output_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'bin').mkdir();(root/'bin/room.ps1').write_text("Write-Output ('x' * 5000)",encoding='utf-8')
            result=RoomRunner(root,limit=100)(['status'])
            self.assertNotEqual(result['exit_code'],0);self.assertLess(len(result['output']),200);self.assertIn('上限',result['output'])
    def test_symlink_document_escape(self):
        with tempfile.TemporaryDirectory() as temporary,tempfile.TemporaryDirectory() as outside:
            root=fixture(Path(temporary));external=Path(outside)/'outside.md';external.write_text('private',encoding='utf-8')
            try:os.symlink(external,root/'drafts/link.md')
            except OSError:self.skipTest('OS does not permit creating symlinks in this account')
            with self.assertRaises(ValueError):RoomStore(root).read_document('drafts','link.md')

if __name__=='__main__':unittest.main()
