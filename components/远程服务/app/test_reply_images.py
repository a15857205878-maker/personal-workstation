import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from reply_queue import ReplyQueue, resume_session
from bot_tasks import DEFAULT_GOAL

PNG=b'\x89PNG\r\n\x1a\n'+b'image-data'
THREAD='01a17e09-26f6-7c43-beef-1c1f59058625'


class Reader:
    def get(self, target):
        return {'id':target,'title':'原会话','cwd':str(Path.cwd())}


class ReplyImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.uploads=self.root/'任务附件';self.uploads.mkdir()
        (self.uploads/'one.png').write_bytes(PNG)
        (self.uploads/'two.jpg').write_bytes(b'\xff\xd8\xffphoto')
        self.q=ReplyQueue(self.root,Reader(),start_worker=False)

    def tearDown(self):
        self.q.close();self.tmp.cleanup()

    def create(self,text='请看图',names=None,request='r1'):
        return self.q.create('web','phone',request,THREAD,text,attachments=names if names is not None else ['one.png'])

    def test_text_and_images_snapshot_same_target_and_survive_upload_change(self):
        job=self.create(names=['one.png','two.jpg'])
        self.assertEqual(job['thread_id'],THREAD)
        self.assertEqual(job['attachments'],['one.png','two.jpg'])
        snapshot=self.q.attachment_path('web','phone',job['id'],'one.png')
        (self.uploads/'one.png').write_bytes(b'changed original')
        self.assertEqual(snapshot.read_bytes(),PNG)
        self.assertNotIn('output',job)
        self.assertNotIn('cwd',job)

    def test_image_only_default_prompt_and_legacy_text(self):
        job=self.create(text='')
        self.assertEqual(job['text'],DEFAULT_GOAL)
        plain=self.q.create('web','phone','text-only',THREAD,'纯文字')
        self.assertEqual(plain.get('attachments',[]),[])

    def test_retry_uses_existing_snapshot_even_if_upload_disappeared(self):
        job=self.create()
        (self.uploads/'one.png').unlink()
        self.assertEqual(self.create()['id'],job['id'])
        with self.assertRaises(ValueError):self.create(names=['two.jpg'])
        with self.assertRaises(ValueError):self.create(text='changed')

    def test_bad_or_non_image_attachments_do_not_enqueue(self):
        (self.uploads/'fake.png').write_text('not an image')
        (self.uploads/'notes.txt').write_text('not an image')
        for names in [['../one.png'],['one.png:secret'],['notes.txt'],['fake.png'],['missing.png'],['one.png']*11,'one.png']:
            with self.subTest(names=names),self.assertRaises(ValueError):
                self.create(names=names)
        self.assertEqual(self.q.list('web','phone'),[])

    def test_attachment_download_is_source_scoped_and_rejects_paths(self):
        job=self.create()
        with self.assertRaises(KeyError):self.q.attachment_path('web','other',job['id'],'one.png')
        with self.assertRaises((KeyError,ValueError,FileNotFoundError)):
            self.q.attachment_path('web','phone',job['id'],'../one.png')

    def test_pending_images_survive_restart_and_execute_once(self):
        job=self.create()
        self.q.close()
        calls=[]
        self.q=ReplyQueue(self.root,Reader(),runner=lambda job,stop:calls.append(job['attachments']) or '收到了',start_worker=False)
        self.q.tick();self.q.tick()
        self.assertEqual(calls,[['one.png']])
        self.assertEqual(self.q.get(job['id'])['status'],'completed')
        self.assertEqual(self.q.attachment_path('web','phone',job['id'],'one.png').read_bytes(),PNG)

    def test_resume_passes_snapshot_images_to_exact_session(self):
        public=self.create(names=['one.png','two.jpg'])
        job=self.q.get(public['id']);commands=[]
        class Process:
            pid=999999
            stdin=io.StringIO()
            stdout=io.StringIO(json.dumps({'type':'thread.started','thread_id':THREAD})+'\n'+json.dumps({'type':'turn.completed'})+'\n')
            def poll(self):return 0
            def wait(self,timeout=None):return 0
        def launch(command,**kwargs):
            commands.append(command)
            Path(job['output']).write_text('收到图片',encoding='utf-8')
            return Process()
        with patch('reply_queue.codex_path',return_value='codex.exe'),patch('reply_queue.subprocess.Popen',side_effect=launch):
            self.assertEqual(resume_session(job,threading.Event()),'收到图片')
        command=commands[0]
        self.assertEqual(command[-2:],[THREAD,'-'])
        self.assertNotIn('--last',command)
        images=[command[i+1] for i,part in enumerate(command) if part=='--image']
        self.assertEqual(images,[str(Path(job['output']).parent/'inputs'/name) for name in job['attachments']])
