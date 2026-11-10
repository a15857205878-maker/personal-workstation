import json,sys,tempfile,threading,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from session_store import SessionStore
import test_api as api_tests
from test_api import FakeClient,await_done

class PartnerNoteTests(unittest.TestCase):
 setUp=api_tests.ApiTests.setUp
 engine=api_tests.ApiTests.engine
 payload=api_tests.ApiTests.payload
 def test_event_keeps_explicit_time_without_duplicate_keyword(self):
  identifier='a'*32;self.sessions.save({'id':identifier,'steps':[]})
  stamp='2026-11-06T00:00:00+00:00'
  self.sessions.event(identifier,{'type':'user_note','text':'补充','at':stamp})
  event=json.loads((self.sessions.base/identifier/'events.jsonl').read_text(encoding='utf-8'))
  self.assertEqual(event['at'],stamp)
 def test_note_ack_matches_persisted_note_and_next_model_context(self):
  entered=threading.Event();release=threading.Event()
  class WaitingClient(FakeClient):
   def complete(inner,*args):
    if not inner.calls:entered.set();release.wait(5)
    return super().complete(*args)
  client=WaitingClient();engine=self.engine(client);engine.start(self.payload())
  try:
   self.assertTrue(entered.wait(2));ack=engine.note('标题保持简短')
   self.assertIn('已加入',ack['message']);saved=engine.status();self.assertEqual(len(saved['notes']),1)
   events=[json.loads(line) for line in (self.sessions.base/saved['id']/'events.jsonl').read_text(encoding='utf-8').splitlines()]
   self.assertEqual(len([event for event in events if event['type']=='user_note']),1)
  finally:release.set();run=await_done(engine)
  self.assertEqual(run['status'],'completed');self.assertIn('标题保持简短',str(client.calls[1]));self.assertEqual(len(client.calls),3)
