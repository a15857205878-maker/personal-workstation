import unittest,tempfile,sys,shutil,json,time,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from room_store import RoomStore
from backend import Bridge

SOURCE=Path(__file__).resolve().parents[1]/'examples/collab'
def fixture(base):
    for name in ('room/messages','card','drafts','persona','bin'):(base/name).mkdir(parents=True,exist_ok=True)
    for name in ('PROTOCOL.md','persona/conductor.md','room/brief.md','room/turn.md'):
        shutil.copy2(SOURCE/name,base/name)
    for p in (SOURCE/'bin').glob('*.ps1'):shutil.copy2(p,base/'bin'/p.name)
    return base
def message(base,number,seat='A',round=1):
    path=base/f'room/messages/20261024T{number:04d}-{seat}-model.md'
    path.write_text(f'---\nseat: {seat}\nmodel: model\nrole: 评审\nround: {round}\nat: 2026-10-24T03:20:11+09:00\nreply-to: earlier.md\n---\n\n主张：M{number:02d}\n<script>alert(1)</script>\n',encoding='utf-8')
    return path

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=fixture(Path(self.temp.name));self.store=RoomStore(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_empty_and_real_brief(self):
        s=self.store.snapshot();self.assertEqual(s['messages'],[]);self.assertEqual(s['turn']['holder'],'A')
        self.assertIn('SUM',[x['id'] for x in s['seats']]);self.assertEqual(s['mode'],'manual')
    def test_order_and_revision(self):
        original=self.store.snapshot()['revision'];message(self.root,2,'B',2);message(self.root,1)
        s=self.store.snapshot();self.assertEqual([x['seat'] for x in s['messages']],['A','B'])
        self.assertNotEqual(original,s['revision']);self.assertEqual(s['messages'][0]['reply_to'],'earlier.md')
    def test_bad_message_names_file(self):
        p=message(self.root,1);p.write_text(p.read_text(encoding='utf-8').replace('seat: A\n',''),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,p.name):self.store.snapshot()
    def test_bad_token(self):
        p=self.root/'room/turn.md';p.write_text(p.read_text(encoding='utf-8').replace('持权: A','持权: Z9'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Z9'):self.store.snapshot()
    def test_document_paths(self):
        (self.root/'drafts/01-note.md').write_text('中文稿件',encoding='utf-8')
        self.assertEqual(self.store.read_document('drafts','01-note.md')['text'],'中文稿件')
        for name in ('../PROTOCOL.md','C:/bad.md','missing.md'):
            with self.assertRaises((ValueError,OSError)):self.store.read_document('drafts',name)
        with self.assertRaises(ValueError):self.store.read_document('messages','anything.md')
    def test_unknown_and_stale_actions(self):
        bridge=Bridge(self.root,executor=lambda args:{'exit_code':0,'output':'ok'})
        self.assertFalse(bridge.call('shell',{'command':'whoami'})['ok'])
        self.assertFalse(bridge.call('start_command',{'command':'next','seat':'../oops','revision':'x'})['ok'])
        old=self.store.snapshot()['revision'];message(self.root,1)
        r=bridge.call('start_command',{'command':'next','seat':'B','revision':old})
        self.assertFalse(r['ok']);self.assertIn('刷新',r['error'])
        self.assertFalse(bridge.call('start_command',{'command':'card','seat':'A','count':0,'revision':old})['ok'])
    def test_async_result_and_recovery(self):
        def execute(args):
            time.sleep(.1)
            return {'exit_code':1,'output':'deliberate failure'}
        bridge=Bridge(self.root,executor=execute)
        started=bridge.call('start_command',{'command':'status'})
        self.assertTrue(started['ok']);self.assertFalse(bridge.call('start_command',{'command':'status'})['ok'])
        while bridge.busy():time.sleep(.02)
        job=bridge.call('command_status',{})['data'];self.assertEqual(job['state'],'failed');self.assertIn('failure',job['output'])
        self.assertTrue(bridge.call('start_command',{'command':'status'})['ok'])
        while bridge.busy():time.sleep(.02)
    def test_bounded_read(self):
        (self.root/'drafts/large.md').write_bytes(b'x'*(600*1024))
        with self.assertRaisesRegex(ValueError,'过大'):self.store.read_document('drafts','large.md')
    def test_overlapping_request_cannot_validate_before_command_lock(self):
        release_first=threading.Event();second_read=threading.Event();resume_second=threading.Event()
        state={'revision':'old','seats':[{'id':'A'},{'id':'B'}]};reads=[];executed=[]
        class Store:
            def snapshot(self):
                value=dict(state);reads.append(1)
                if len(reads)==2:second_read.set();resume_second.wait(2)
                return value
        def execute(args):
            executed.append(args);release_first.wait(2);state['revision']='new'
            return {'exit_code':0,'output':'ok'}
        bridge=Bridge(self.root,executor=execute);bridge.store=Store()
        self.assertTrue(bridge.call('start_command',{'command':'next','seat':'B','revision':'old'})['ok'])
        second={}
        def overlap():second.update(bridge.call('start_command',{'command':'next','seat':'A','revision':'old'}))
        thread=threading.Thread(target=overlap);thread.start()
        deadline=time.monotonic()+2
        while thread.is_alive() and not second_read.is_set() and time.monotonic()<deadline:time.sleep(.01)
        release_first.set()
        while bridge.busy() and time.monotonic()<deadline:time.sleep(.01)
        resume_second.set();thread.join(2)
        while bridge.busy():time.sleep(.01)
        self.assertFalse(second['ok']);self.assertEqual(len(executed),1)

if __name__=='__main__':unittest.main()
