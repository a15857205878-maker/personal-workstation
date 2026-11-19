import unittest,tempfile,sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from session_store import SessionStore

class CenterIndexTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
 def seed(self,archived=False):
  cid='a'*32;tid='b'*32;rid='c'*32;pid='d'*32
  raw=b'fixture';name='协作成果-'+hashlib.sha256(raw).hexdigest()[:16]+'.docx';folder=self.data/'collaboration-artifacts'/rid;folder.mkdir(parents=True);(folder/name).write_bytes(raw)
  SessionStore(self.data/'sessions').save(dict(id=rid,title='原子运行',status='completed',steps=[],roles={'A':dict(id=pid,name='原模型',model='model',base_url='https://private')},files=[dict(name=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest())],call_count=1,call_limit=1))
  job=dict(title='周报',instruction='PRIVATE',primary_id=pid,roles={'A':dict(id=pid,name='原模型',model='model')},state='completed',call_count=1,run_id=rid)
  SessionStore(self.data/'agent-center/conversations').save(dict(id=cid,title='本周项目',status='idle',steps=[],roles={'A':dict(id=pid,name='原模型',base_url='PRIVATE')},turns=[dict(id=tid,text='PRIVATE',kind='execute',state='completed',jobs=[job],call_count=1)],call_count=1,call_limit=30,archived=archived))
  return cid,tid,rid,name
 def test_artifact_owned_by_center_with_no_duplicate_and_original_path(self):
  from artifact_browser import ArtifactBrowser
  cid,tid,rid,name=self.seed();b=ArtifactBrowser(self.data);items=b.list([])['items']
  self.assertEqual(len(items),1);f=items[0];self.assertEqual(f['source_kind'],'center');self.assertEqual((f['conversation_id'],f['turn_id'],f['run_id']),(cid,tid,rid));self.assertEqual(f['job_title'],'周报');self.assertEqual(f['owner_name'],'原模型')
  self.assertEqual(b.path(f['id']),self.data/'collaboration-artifacts'/rid/name)
  self.assertNotIn('PRIVATE',json.dumps(f));self.assertNotIn('base_url',json.dumps(f))
 def test_overview_and_butler_count_current_center_separately_from_history(self):
  from backend import Bridge
  from butler_center import ButlerCenter
  self.seed();b=Bridge(self.data/'missing',data_dir=self.data)
  try:
   r=b.call('workstation_overview',{});self.assertTrue(r['ok'],r);v=r['data']
   self.assertEqual(v['counts']['conversations'],1);self.assertEqual(v['counts']['active'],0);self.assertEqual(v['counts']['deliveries'],1);self.assertIsNone(b._auto)
   p=ButlerCenter(data_dir=self.data).snapshot(v);self.assertEqual(p['counts']['conversations'],1);self.assertEqual(p['recent'][0]['id'],'a'*32)
   today=b.call('workstation_butler_status',{})['data']['today']
   self.assertEqual(today['review']['count'],1);self.assertEqual(today['review']['items'][0]['turn_id'],'b'*32)
   self.assertNotIn('PRIVATE',json.dumps(today));self.assertIsNone(b._auto)
  finally:b.close_station()
 def test_archive_excluded_from_current_but_file_stays(self):
  from center_index import read_center
  from artifact_browser import ArtifactBrowser
  self.seed(True);v=read_center(self.data,include_today=True);self.assertEqual(v['counts']['conversations'],0);self.assertTrue(ArtifactBrowser(self.data).list([])['items'][0]['conversation_archived'])
  self.assertTrue(all(group['count']==0 for group in v['today'].values()))
 def test_today_groups_exact_turns_and_keeps_earlier_unfinished_work(self):
  from center_index import read_center
  from credential_store import atomic_json
  cid,tid,rid,name=self.seed()
  sessions=SessionStore(self.data/'agent-center/conversations');session=sessions.load(cid)
  def other(letter,state,kind='execute'):
   return dict(id=letter*32,kind=kind,text='PRIVATE',at='2000-01-01T00:00:00+00:00',state=state,jobs=[],call_count=0)
  session['turns'].extend([other('1','prepared'),other('2','running'),other('3','running','chat'),other('4','cancelled')])
  sessions.save(session)
  today=read_center(self.data,include_today=True)['today']
  self.assertEqual({key:[row['turn_id'] for row in group['items']] for key,group in today.items()},
                   {'prepared':['1'*32],'active':['2'*32],'review':[tid],'accepted':[]})
  child=SessionStore(self.data/'sessions');run=child.load(rid);run['updated']='2000-01-01T00:00:00+00:00'
  atomic_json(child._directory(rid)/'session.json',run)
  self.assertEqual(read_center(self.data,include_today=True)['today']['review']['count'],0)
  child.save(run)
  (self.data/'collaboration-artifacts'/rid/name).write_bytes(b'truncated elsewhere')
  self.assertEqual(read_center(self.data,include_today=True)['today']['review']['count'],0)
 def test_missing_child_is_visible_and_never_written(self):
  from center_index import read_center
  self.seed();p=self.data/'sessions'/('c'*32)/'session.json';p.unlink();before={str(f):f.read_bytes() for f in self.data.rglob('*.json')};v=read_center(self.data)
  self.assertTrue(v['warnings']);self.assertEqual(v['counts']['attention'],1);self.assertTrue(v['rows'][0]['can_open']);self.assertEqual(before,{str(f):f.read_bytes() for f in self.data.rglob('*.json')})
 def test_retry_success_resolves_original_failure_without_changing_history(self):
  from center_index import read_center
  cid,tid,rid,name=self.seed();s=SessionStore(self.data/'agent-center/conversations');v=s.load(cid);v['turns'][0].update(state='failed',jobs=[],kind='chat',run_id=None)
  v['turns'][0]['error']='失败';v['turns'].append(dict(id='e'*32,text='PRIVATE',kind='discuss',state='completed',call_count=1,retry_of=dict(turn_id=tid,item='message:'+('f'*32))))
  # A recorded failed member row is needed to map this exact recovery target.
  chatid='1'*32;v['turns'][0]['run_id']=chatid
  SessionStore(self.data/'agent-center/negotiations').save(dict(id=chatid,title='讨论',status='failed',steps=[],messages=[dict(id='f'*32,seat='A',state='failed',error='失败')],roles={},call_count=1,call_limit=30))
  s.save(v);index=read_center(self.data);self.assertEqual(index['counts']['attention'],0)
 def test_old_planning_rejection_does_not_hide_new_delivery(self):
  from center_index import read_center
  cid,tid,_,_=self.seed()
  store=SessionStore(self.data/'agent-center/conversations')
  session=store.load(cid)
  old=dict(id='e'*32,kind='execute',drafted=True,text='早先的草案',state='failed',jobs=[],call_count=1,
           error='协商方案未通过校验：模型未返回可读取的分工 JSON。未执行任何子任务。')
  session['turns'].insert(0,old)
  store.save(session)
  original=(store._directory(cid)/'session.json').read_bytes()
  index=read_center(self.data)
  self.assertFalse(index['rows'][0]['needs_attention'])
  self.assertEqual(index['rows'][0]['turn_id'],tid)
  self.assertEqual((store._directory(cid)/'session.json').read_bytes(),original)
  session['turns'].reverse()
  store.save(session)
  self.assertTrue(read_center(self.data)['rows'][0]['needs_attention'])
  session['turns'].reverse()
  old.update(drafted=False,error='执行失败，请核对连接')
  store.save(session)
  self.assertTrue(read_center(self.data)['rows'][0]['needs_attention'])
 def test_center_files_survive_child_history_limit(self):
  from artifact_browser import ArtifactBrowser
  from credential_store import atomic_json
  cid,tid,rid,name=self.seed();store=SessionStore(self.data/'sessions');original=store.load(rid);original['updated']='2000-01-01T00:00:00+00:00';atomic_json(store._directory(rid)/'session.json',original)
  for i in range(101):store.save(dict(id=f'{i:032x}',title='较新历史',status='completed',steps=[],call_count=1,call_limit=1))
  self.assertEqual(ArtifactBrowser(self.data).list([])['items'][0]['conversation_id'],cid)
 def test_direct_child_finishes_without_opening_conversation_or_writing_parent(self):
  from center_index import read_center
  cid,tid,rid,name=self.seed();store=SessionStore(self.data/'agent-center/conversations');root=store.load(cid)
  root['turns']=[dict(id=tid,text='原需求',kind='discuss',state='running',call_count=0,run_id=rid)];root['status']='running';store.save(root)
  child=SessionStore(self.data/'agent-center/chats');run=dict(id=rid,title='补回',steps=[],status='idle',call_count=1,call_limit=30,messages=[dict(id='f'*32,seat='U',state='completed',content='原需求')]);child.save(run)
  before=(store._directory(cid)/'session.json').read_bytes();index=read_center(self.data)
  self.assertEqual(index['counts']['active'],0);self.assertEqual(index['rows'][0]['status'],'completed');self.assertEqual(index['rows'][0]['call_count'],1)
  run['status']='failed';run['messages'].append(dict(id='e'*32,seat='A',state='failed',error='连接失败'));child.save(run)
  index=read_center(self.data);self.assertEqual(index['counts']['attention'],1);self.assertEqual(index['counts']['active'],0);self.assertEqual(before,(store._directory(cid)/'session.json').read_bytes())

if __name__=='__main__':unittest.main()
