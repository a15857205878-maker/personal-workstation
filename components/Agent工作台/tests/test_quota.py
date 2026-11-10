from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task_station.quota import QuotaStore

class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'claude-quota.json'
        self.now=datetime(2026,11,2,15,30,tzinfo=timezone.utc)
        self.store=QuotaStore(self.path,clock=lambda:self.now)
    def tearDown(self):self.tmp.cleanup()
    def sample(self,**extra):
        return dict(schema_version=1,state='limited',checked_at=self.now.isoformat(),reset_at=(self.now+timedelta(hours=4)).isoformat(),reset_text='04:30',source_url='https://claude.ai/new',source_text='您的使用限额将于04:30重置。',**extra)
    def test_roundtrip_and_read_only(self):
        self.store.save(self.sample());raw=self.path.read_bytes()
        got=self.store.read();self.assertEqual(got['effective_state'],'limited');self.assertEqual(got['state'],'limited')
        self.assertEqual(self.path.read_bytes(),raw)
    def test_missing_and_bad_files_do_not_crash(self):
        self.assertEqual(self.store.read()['effective_state'],'unknown')
        for raw in [b'not json',b'[]',b'x'*16385]:
            self.path.write_bytes(raw);self.assertEqual(self.store.read()['effective_state'],'read_failed')
    def test_reset_elapsed_requires_recheck_and_old_record_is_stale(self):
        self.store.save(self.sample());self.now+=timedelta(hours=5)
        self.assertEqual(self.store.read()['effective_state'],'due')
        self.now+=timedelta(days=2);self.assertEqual(self.store.read()['effective_state'],'stale')
    def test_reject_invalid_source_timestamps_and_status(self):
        for key,value in [('source_url','https://claude.ai.evil.invalid/'),('source_url','http://claude.ai/new'),('checked_at','2026-11-03T01:30:00'),('state','unlimited'),('source_text','x'*1201),('reset_at','bad')]:
            data=self.sample();data[key]=value
            with self.assertRaises(ValueError):self.store.save(data)
        self.assertFalse(self.path.exists())
    def test_failed_check_is_unknown_and_does_not_claim_available(self):
        data=self.sample();data.update(state='login_required',reset_at=None,source_text='需要登录')
        self.store.save(data);self.assertEqual(self.store.read()['effective_state'],'login_required')

if __name__=='__main__':unittest.main()

