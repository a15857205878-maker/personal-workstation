import tempfile,unittest,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from town_adapter import TownAdapter
from focus_summary import focus_summary

class FocusSummaryTests(unittest.TestCase):
 def test_cold_active_is_unknown_and_does_not_claim_clock_is_running(self):
  self.assertEqual(focus_summary(dict(active=True,running=True,remaining=100,duration=25),False)['kind'],'unknown')
  self.assertEqual(focus_summary(dict(active=True,running=True,remaining=100,duration=25),True)['kind'],'running')
  self.assertEqual(focus_summary(dict(active=True,running=False,remaining=100,duration=25),True)['kind'],'paused')
 def test_adapter_reuses_existing_clock_and_drops_task_text(self):
  with tempfile.TemporaryDirectory() as folder:
   adapter=TownAdapter(base=Path(folder));self.assertEqual(adapter.focus_summary()['kind'],'idle');self.assertFalse((Path(folder)/'data').exists())
   calls=[]
   def call(a,p):calls.append((a,p));return {'ok':True,'data':{'focus':dict(active=True,running=True,remaining=120,duration=25,task='PRIVATE')}}
   adapter._bridge=SimpleNamespace(call=call)
   result=adapter.focus_summary();self.assertEqual(result['remaining'],120);self.assertEqual(calls,[('focus_state',{})]);self.assertNotIn('PRIVATE',json.dumps(result))
if __name__=='__main__':unittest.main()
