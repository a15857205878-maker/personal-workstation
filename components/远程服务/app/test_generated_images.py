import base64
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
import http.client
import threading
from pathlib import Path
from session_reader import CodexSessionReader


class GeneratedImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
        (self.home/'sessions').mkdir();self.log=self.home/'sessions'/'test.jsonl'
        with closing(sqlite3.connect(self.home/'state_5.sqlite')) as db, db:
            db.execute('CREATE TABLE threads(id,title,cwd,updated_at,rollout_path,archived)')
            db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',('one','test',str(self.home),0,str(self.log),0))
        self.reader=CodexSessionReader(self.home)
        self.image=b'\x89PNG\r\n\x1a\n'+b'x'*900000

    def tearDown(self):self.tmp.cleanup()

    def write(self,call='const r=await tools.image_gen__imagegen({}); generatedImage(r);',mime='image/png'):
        entries=[{'type':'response_item','payload':{'type':'custom_tool_call','name':'exec','call_id':'ok','input':call}},
                 {'type':'response_item','payload':{'type':'custom_tool_call_output','call_id':'ok','output':[
                     {'type':'input_text','text':'PRIVATE_TOOL_TEXT'},
                     {'type':'input_image','image_url':'data:'+mime+';base64,'+base64.b64encode(self.image).decode()}]}},
                 {'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final','content':[{'type':'output_text','text':'done'}]}}]
        self.log.write_text(''.join(json.dumps(e)+'\n' for e in entries),encoding='utf-8')

    def test_large_generated_image_is_public_without_tool_text_or_base64(self):
        self.write();history=self.reader.history('one')
        images=[m for m in history['messages'] if m.get('images')]
        self.assertEqual(len(images),1)
        self.assertNotIn('PRIVATE_TOOL_TEXT',json.dumps(history));self.assertNotIn('base64',json.dumps(history))
        desc=images[0]['images'][0]
        data,mime=self.reader.generated_image('one',int(images[0]['id']),desc['index'])
        self.assertEqual(data,self.image);self.assertEqual(mime,'image/png')
        earlier=self.reader.history('one',before=int(history['messages'][-1]['id']))
        self.assertEqual(len([m for m in earlier['messages'] if m.get('images')]),1)

    def test_unrelated_tool_images_and_invalid_mime_are_not_exposed(self):
        for call,mime in [('image(await tools.view_image({}));','image/png'),
                          ('// tools.image_gen__imagegen(); generatedImage()\nimage(await tools.view_image({}));','image/png'),
                          ('const r=await tools.image_gen__imagegen({}); generatedImage(r); image(await tools.view_image({}));','image/png'),
                          ('generatedImage(await tools.image_gen__imagegen({}));','image/svg+xml')]:
            self.write(call,mime)
            self.assertFalse(any(m.get('images') for m in self.reader.history('one')['messages']))

    def test_exact_record_session_and_index_required(self):
        self.write()
        for thread,offset,index in [('missing',0,1),('one',0,1),('one',-1,0),('one',3,0)]:
            with self.assertRaises((ValueError,KeyError,FileNotFoundError)):
                self.reader.generated_image(thread,offset,index)

    def test_generation_call_before_page_window_still_proves_image(self):
        self.write()
        rows=self.log.read_text(encoding='utf-8').splitlines()
        padding=json.dumps({'type':'ignored','padding':'x'*(17*1024*1024)})
        self.log.write_text('\n'.join([rows[0],padding]+rows[1:])+'\n',encoding='utf-8')
        page=self.reader.history('one')
        msg=next(m for m in page['messages'] if m.get('images'))
        self.assertEqual(self.reader.generated_image('one',int(msg['id']),1)[0],self.image)

    def test_image_http_requires_pairing_and_returns_only_image(self):
        from transfer import create_server
        self.write();msg=next(m for m in self.reader.history('one')['messages'] if m.get('images'))
        with patch('transfer.CodexSessionReader',return_value=self.reader),patch('transfer.TaskManager.start'),patch('transfer.ReplyQueue.start'):
            server=create_server('127.0.0.1',0,self.home/'app'/'photos','test-image')
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            route='/api/bot/generated-image?thread_id=one&offset='+msg['id']+'&index=1&token='
            for token,expected in [('wrong',403),('test-image',200)]:
                c=http.client.HTTPConnection(*server.server_address,timeout=5);c.request('GET',route+token)
                r=c.getresponse();data=r.read();self.assertEqual(r.status,expected)
                if expected==200:
                    self.assertEqual(data,self.image);self.assertEqual(r.getheader('Content-Type'),'image/png')
                    self.assertEqual(r.getheader('Cache-Control'),'no-store')
                c.close()
        finally:server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main()
