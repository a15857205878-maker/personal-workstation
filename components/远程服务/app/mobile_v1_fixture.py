"""Explicit test-only remote gateway. No models, source data, credentials or apps."""
import copy,threading,io,zipfile,base64,json,importlib.util
from pathlib import Path

class MobileFixture:
    def __init__(self):
        self.lock=threading.RLock();self.writes=[];self.offline=False
        self.tasks={
            'a'*32:dict(id='a'*32,title='整理本周的项目进展',instruction='汇总工作站维护进展，整理为一份周报。',status='执行中',role='writer',mode='api',events=[{'message':'已开始整理资料'}],result='正在整理任务记录…'),
            'b'*32:dict(id='b'*32,title='帮我准备一份会议提纲',instruction='整理明天会议需要讨论的内容。',status='草稿',role='writer',mode='api'),
            'c'*32:dict(id='c'*32,title='归纳文档中的关键结论',instruction='提取关键结论。',status='已完成',task_type='text',role='writer',mode='api',result='已完成整理，关键结论分为三个部分。')}
        self.sheet_spec=json.dumps({'version':1,'sheets':[{'name':'预算','columns':['项目','数量','单价','小计'],'rows':[['材料',2,12.5,{'formula':'=B2*C2'}],['配件',3,8,{'formula':'=B3*C3'}],['合计',None,None,{'formula':'=SUM(D2:D3)'}]]}]},ensure_ascii=False)
        spec_value=json.loads(self.sheet_spec);spec_value['sheets'].append({'name':'备注','columns':['说明'],'rows':[['只读预览验证']]});self.sheet_spec=json.dumps(spec_value,ensure_ascii=False)
        exporter=Path(__file__).resolve().parents[2]/'Agent工作台/task_station/spreadsheet_export.py'
        spec=importlib.util.spec_from_file_location('fixture_xlsx',exporter);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);self.spreadsheet_bytes=module.spreadsheet_bytes(self.sheet_spec)
        self.tasks['9'*32]=dict(id='9'*32,title='项目预算表',instruction='材料2件每件12.5元，配件3件每件8元，制作预算表',task_type='xlsx',role='writer',mode='api',status='结果待确认',result=self.sheet_spec)
        self.collabs={};self.receipts=[];self.counter=0;self.results={}
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('说明.txt','隔离压缩验收')
        self.pack_bytes=buffer.getvalue();self.program=None
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('word/document.xml','<document>隔离Word下载验收</document>')
        self.document_bytes=buffer.getvalue()
        self.profiles=[{'id':'a','name':'主执行模型','model':'Fixture A'},{'id':'b','name':'审查模型','model':'Fixture B'}]
    def call(self,action,payload=None,request_id=None):
        payload=payload or {}
        with self.lock:
            if self.offline and action not in ('app_list','app_launch'):return {'ok':False,'error':'电脑工作台未连接，请打开工作站后重新检查。'}
            if action=='catalog':result={'task_catalog':{'tasks':[{'id':'document','label':'制作文档','agents':[{'role_ref':'writer','label':'文档 Agent'},{'role_ref':'manual','label':'手动交接'}]},{'id':'pptx','label':'生成PPT','agents':[{'role_ref':'writer','label':'文档 Agent'}]}]+[{'id':identifier,'label':label,'agents':[{'role_ref':'manual','label':'手动交接'}]} for identifier,label in [('xlsx','生成Excel'),('image','生成图片'),('research','查找资料'),('web_check','检查网页'),('web_edit','修改网页'),('software_operation','软件操作'),('software_error','处理软件报错')]],'roles':{'writer':{'can_run':True},'manual':{'can_run':False}}},'profiles':self.profiles,'limits':{'max_rounds':10,'max_calls':30,'max_tokens':4096,'max_seconds':600}}
            elif action=='list':result={'tasks':list(self.tasks.values()),'collaborations':list(self.collabs.values()),'receipts':self.receipts}
            elif action=='pack_preview':result={'preview_id':'e'*32,'files':[{'name':'说明.txt','size':18}],'count':1,'total_size':18,'source':'电脑上次选定文件'}
            elif action=='task_artifact' and payload.get('name')=='测试预算.xlsx':result={'name':'测试预算.xlsx','size':len(self.spreadsheet_bytes),'content_base64':base64.b64encode(self.spreadsheet_bytes).decode()}
            elif action=='task_artifact' and payload.get('name')=='测试文档.docx':result={'name':'测试文档.docx','size':len(self.document_bytes),'content_base64':base64.b64encode(self.document_bytes).decode()}
            elif action=='task_artifact':result={'name':'测试资料.zip','size':len(self.pack_bytes),'content_base64':base64.b64encode(self.pack_bytes).decode()}
            elif action=='app_list':result={'apps':[{'id':'workbench','name':'打开测试工作站'}]}
            elif action in ('task_get','collaboration_get'):result=(self.tasks if action=='task_get' else self.collabs)[payload['id']]
            else:
                if request_id in self.results:return {'ok':True,'data':copy.deepcopy(self.results[request_id])}
                self.writes.append({'action':action,'payload':copy.deepcopy(payload),'request_id':request_id})
                if action=='task_create':
                    self.counter+=1;identifier=f'{self.counter:032x}';self.tasks[identifier]=dict(id=identifier,title=payload['instruction'],instruction=payload['instruction'],status='草稿',role=payload['role'],task_type=payload['task_type'],materials=payload.get('materials',''),requirements=payload.get('requirements',''),mode='api');result=self.tasks[identifier]
                elif action in ('task_submit','task_cancel','task_complete'):
                    task=self.tasks[payload['id']];task['status']={'task_submit':'执行中','task_cancel':'已取消','task_complete':'已完成'}[action];result=task
                elif action=='task_export_document':
                    task=self.tasks[payload['id']];task['files']=[{'name':'测试文档.docx','size':len(self.document_bytes)}];task['events']=[{'message':'已生成Word文件：测试文档.docx'}];result=task
                elif action=='task_export_spreadsheet':
                    task=self.tasks[payload['id']];task['files']=[{'name':'测试预算.xlsx','size':len(self.spreadsheet_bytes)}];task['events']=[{'message':'已生成Excel文件：测试预算.xlsx'}];result=task
                elif action=='task_note':
                    task=self.tasks[payload['id']];task.setdefault('remote_notes',[]).append({'text':payload['text']});result=task
                elif action=='collaboration_start':
                    identifier=format(0xdddddddddddddddddddddddddddddddd+len(self.collabs),'032x');self.collabs[identifier]=dict(id=identifier,title=payload['task'],task=payload['task'],status='running',stage='提案',call_count=1,call_limit=payload['call_limit'],steps=[{'id':'fixture-step','seat':'A','model':'Fixture A','round':1,'stage':'提案','state':'completed','content':'隔离验收：已整理任务重点。'}]);result=self.collabs[identifier]
                elif action=='collaboration_stop':self.collabs[payload['id']]['status']='cancelled';result=self.collabs[payload['id']]
                elif action=='pack_start':
                    if self.program is None:self.program=dict(id='f'*32,title='文件打包',instruction='打包电脑上次选定文件',task_type='program_pack',role='tools_pack',mode='program',status='已完成',result='压缩包已生成并校验',error='',files=[{'name':'测试资料.zip','size':len(self.pack_bytes)}]);self.tasks[self.program['id']]=self.program
                    result=self.program
                elif action=='app_launch':result={'message':'Fixture launch accepted'}
                elif action=='collaboration_note':result={}
                else:raise AssertionError('Fixture does not implement '+action)
                self.results[request_id]=copy.deepcopy(result)
                self.receipts.append({'request_id':request_id,'state':'confirmed'})
            return {'ok':True,'data':copy.deepcopy(result)}
