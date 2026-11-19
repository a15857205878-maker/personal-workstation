import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from center_remote import dispatch,FIELDS,READS,REQUIRED
class MobileResults(unittest.TestCase):
 def test_read_contract(self):
  self.assertEqual(FIELDS['center_results'],set());self.assertIn('center_results',READS);self.assertEqual(REQUIRED['center_results'],set())
 def test_bounded_projection_not_paths_or_fake_success(self):
  class Gateway:
   calls=[]
   def _call(self,a,p):
    self.calls.append((a,p))
    if a=='api_center_bootstrap':return {'sessions':[{'id':str(i),'title':'Group','archived':i==0} for i in range(40)]}
    if p['id']=='2':raise ValueError('unreadable')
    return {'id':p['id'],'title':'Group','status':'running','turns':[{'id':'turn','jobs':[{'title':'Document','run':{'id':'run'+p['id'],'status':'failed','roles':{'A':{'name':'Member','model':'test','api_key':'secret'}},'files':[{'name':'result.docx','size':12,'path':'C:/secret'},{'name':'../secret','size':3}]}}]}]}
  g=Gateway();value=dispatch(g,'center_results',{});self.assertLessEqual(len(g.calls),25)
  self.assertTrue(value['limited']);self.assertTrue(value['warnings']);self.assertEqual(len(value['items']),23)
  item=value['items'][0];self.assertEqual(item['status'],'failed');self.assertEqual(item['owner'],'Member')
  self.assertNotIn('secret',str(value));self.assertNotIn('content_base64',str(value));self.assertNotIn('0',[x['conversation_id'] for x in value['items']])
 def test_no_files_no_completed_delivery(self):
  class Gateway:
   def _call(self,a,p):return {'sessions':[{'id':'x'}]} if a=='api_center_bootstrap' else {'id':'x','title':'Empty','status':'running','turns':[{'id':'t','run':{'id':'r','status':'running','files':[]}}]}
  self.assertEqual(dispatch(Gateway(),'center_results',{})['items'],[])
if __name__=='__main__':unittest.main()
