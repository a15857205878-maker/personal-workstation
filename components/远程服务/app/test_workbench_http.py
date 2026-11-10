import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from transfer import create_server


class WorkbenchHTTPTests(unittest.TestCase):
    def test_paired_room_summary_uses_actual_gateway_whitelist_without_private_fields(self):
        import sys,time
        station=Path(__file__).resolve().parents[2]/'Agent工作台'
        sys.path.insert(0,str(station))
        from remote_gateway import RemoteGateway
        from workbench_proxy import WorkbenchProxy
        from types import SimpleNamespace
        bridge=SimpleNamespace(call=lambda action,payload:{'ok':True,'data':dict(overview_state='ready',observed_at=time.time(),counts=dict(tasks=1,collaborations=0,active=1,attention=0),notices=[],title='PRIVATE',secret='SECRET')})
        gateway=RemoteGateway(bridge,Path(self.temp.name)/'room-gateway',port=0)
        self.server.workbench=WorkbenchProxy(Path(self.temp.name),Path(self.temp.name)/'uploads',transport=lambda action,payload,rid:gateway.rpc({'action':action,'payload':payload,'request_id':rid}))
        self.assertEqual(self.request('/api/workbench?action=room_status')[0],403)
        code,raw=self.request('/api/workbench?action=room_status&token=paired-test')
        self.assertEqual(code,200);data=json.loads(raw);self.assertTrue(data['ok']);self.assertEqual(data['data']['counts']['active'],1)
        self.assertNotIn(b'PRIVATE',raw);self.assertNotIn(b'SECRET',raw)
        self.assertEqual(self.request('/api/workbench?action=room_status&token=paired-test&path=private')[0],400)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = create_server('127.0.0.1', 0, Path(self.temp.name) / 'photos', 'paired-test')
        self.proxy = Mock()
        self.proxy.call.return_value = {'ok': True, 'data': {'profiles': []}}
        self.server.workbench = self.proxy
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        c = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        default = {'Content-Type': 'application/json'}
        default.update(headers or {})
        c.request('POST' if payload is not None else 'GET', path, body=json.dumps(payload) if payload is not None else None, headers=default)
        r = c.getresponse()
        status, raw = r.status, r.read()
        c.close()
        return status, raw

    def test_session_actions_asset_requires_pairing_and_has_no_execution_endpoint(self):
        self.assertEqual(self.request('/sessions')[0],403)
        code,body=self.request('/sessions?token=paired-test')
        self.assertEqual(code,200)
        self.assertIn(b'workstation-session-collaboration',body)
        self.assertIn(b'id="session-actions-script"',body)
        self.proxy.call.assert_not_called()

    def test_collaboration_file_preview_download_has_explicit_owned_source(self):
        import base64
        from test_file_review import xlsx
        raw=xlsx();self.proxy.call.return_value={'ok':True,'data':{'name':'report.xlsx','content_base64':base64.b64encode(raw).decode()}}
        prefix='?token=paired-test&id='+'a'*32+'&name=report.xlsx&kind=collaboration'
        code,body=self.request('/api/workbench-artifact'+prefix);self.assertEqual(code,200);self.assertEqual(body,raw)
        self.proxy.call.assert_called_with('collaboration_artifact',{'id':'a'*32,'name':'report.xlsx'})
        self.proxy.call.reset_mock();code,body=self.request('/api/workbench-sheet'+prefix);self.assertEqual(code,200);self.assertEqual(json.loads(body)['kind'],'table')
        self.proxy.call.assert_called_with('collaboration_artifact',{'id':'a'*32,'name':'report.xlsx'})
        self.proxy.call.reset_mock();self.assertEqual(self.request('/api/workbench-artifact'+prefix.replace('kind=collaboration','kind=unknown'))[0],400);self.proxy.call.assert_not_called()
        self.assertEqual(self.request('/api/workbench?action=collaboration_artifact&token=paired-test&id='+'a'*32)[0],400)

    def test_pairing_and_origin_are_required_before_forwarding(self):
        self.assertEqual(self.request('/api/workbench?action=catalog')[0], 403)
        self.assertEqual(self.request('/api/workbench?token=paired-test', {'action': 'task_submit', 'payload': {'id': 'a'*32}, 'request_id': 'test-1'}, {'Origin': 'https://attacker.example'})[0], 403)
        self.proxy.call.assert_not_called()

    def test_workbench_xlsx_native_view_is_paired_owned_read_only_and_does_not_convert(self):
        import base64
        from test_file_review import xlsx
        path='/api/workbench-sheet?token=paired-test&id='+'a'*32+'&name=report.xlsx'
        self.assertEqual(self.request('/api/workbench-sheet')[0],403)
        self.assertEqual(self.request(path,headers={'Origin':'https://outside.example'})[0],403)
        self.proxy.call.assert_not_called()
        raw=xlsx();self.proxy.call.return_value={'ok':True,'data':{'name':'report.xlsx','content_base64':base64.b64encode(raw).decode()}}
        code,body=self.request(path);self.assertEqual(code,200);d=json.loads(body);self.assertEqual(d['kind'],'table');self.assertEqual(d['path'],'report.xlsx');self.assertEqual(d['sheets'][0]['rows'][0],['名称','0']);self.proxy.call.assert_called_once_with('task_artifact',{'id':'a'*32,'name':'report.xlsx'})
        self.proxy.call.reset_mock()
        for suffix in ['&name=../private.xlsx','&name=report.docx']:
            code,_=self.request('/api/workbench-sheet?token=paired-test&id='+'a'*32+suffix);self.assertEqual(code,400)
        self.proxy.call.assert_not_called()
        self.proxy.call.return_value={'ok':False,'error':'target_not_remote_owned'}
        self.assertEqual(self.request(path)[0],400)

    def test_pc_file_search_download_is_paired_and_cannot_add_roots_remotely(self):
        from pc_files import ComputerFiles
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'work') as raw:
            root=Path(raw);folder=root/'chosen';folder.mkdir();(folder/'report.txt').write_bytes(b'pc original')
            self.server.pc_files=ComputerFiles(root/'service');self.server.pc_files.add_root(folder)
            self.assertEqual(self.request('/api/pc-files/search?q=report')[0],403)
            self.assertEqual(self.request('/api/pc-files/search?token=paired-test&q=report',headers={'Origin':'https://outside.example'})[0],403)
            code,body=self.request('/api/pc-files/search?token=paired-test&q=report');self.assertEqual(code,200);result=json.loads(body);self.assertNotIn(str(root),body.decode());self.assertEqual(len(result['files']),1)
            ticket=result['files'][0]['id'];self.assertEqual(self.request('/api/pc-files/download?token=paired-test&id='+ticket),(200,b'pc original'))
            self.assertNotEqual(self.request('/api/pc-files/roots?token=paired-test',{'path':str(folder)})[0],200)
            self.assertEqual(self.request('/api/pc-files/download?token=paired-test&id=../secret')[0],400)

    def test_library_browse_without_query_only_returns_the_dedicated_folder(self):
        from pc_files import ComputerFiles
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'work') as raw:
            root=Path(raw);library=root/'手机文件库';other=root/'other';library.mkdir();other.mkdir();(library/'report.txt').write_bytes(b'library original');(other/'private.txt').write_text('not in library')
            self.server.pc_files=ComputerFiles(root/'service');self.server.pc_files.add_root(other);self.server.pc_files.set_library(library)
            code,body=self.request('/api/pc-files/library?token=paired-test');self.assertEqual(code,200);data=json.loads(body);self.assertEqual([f['name'] for f in data['files']],['report.txt']);self.assertEqual(len(data['roots']),1)
            code,raw=self.request('/api/pc-files/download?token=paired-test&id='+data['files'][0]['id']);self.assertEqual((code,raw),(200,b'library original'))
            self.assertEqual(self.request('/api/pc-files/library')[0],403)
    def test_content_mode_uses_same_pairing_and_original_download(self):
        from pc_files import ComputerFiles
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);folder=root/'files';folder.mkdir();source=folder/'notes.md'
            source.write_text('first\ncoastal theme',encoding='utf-8')
            self.server.pc_files=ComputerFiles(root/'service');self.server.pc_files.set_library(folder)
            endpoint='/api/pc-files/library?mode=content&q=coastal'
            self.assertEqual(self.request(endpoint)[0],403)
            self.assertEqual(self.request(endpoint+'&token=paired-test',headers={'Origin':'https://outside.example'})[0],403)
            code,raw=self.request(endpoint+'&token=paired-test');self.assertEqual(code,200)
            row=json.loads(raw)['files'][0];self.assertEqual(row['location'],'第2行')
            self.assertNotIn(str(root),raw.decode('utf-8'))
            self.assertEqual(self.request('/api/pc-files/download?token=paired-test&id='+row['id']),(200,source.read_bytes()))

    def test_get_cannot_execute_and_post_forwards_exact_envelope(self):
        code, raw = self.request('/api/workbench?token=paired-test&action=catalog')
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(raw)['ok'])
        self.proxy.call.assert_called_with('catalog', {})
        self.assertEqual(self.request('/api/workbench?token=paired-test&action=task_submit&id='+'a'*32)[0], 400)
        body = {'action': 'task_submit', 'payload': {'id': 'a'*32}, 'request_id': 'test-1'}
        self.assertEqual(self.request('/api/workbench?token=paired-test', body)[0], 200)
        self.proxy.call.assert_called_with('task_submit', {'id': 'a'*32}, 'test-1')

    def test_pack_preview_is_read_only_and_start_requires_post(self):
        self.assertEqual(self.request('/api/workbench?token=paired-test&action=pack_preview')[0], 200)
        self.proxy.call.assert_called_with('pack_preview', {})
        self.assertEqual(self.request('/api/workbench?token=paired-test&action=pack_start')[0], 400)
        body = {'action': 'pack_start', 'payload': {'preview_id': 'e'*32}, 'request_id': 'pack-1'}
        self.assertEqual(self.request('/api/workbench?token=paired-test', body)[0], 200)
        self.proxy.call.assert_called_with('pack_start', {'preview_id': 'e'*32}, 'pack-1')

    def test_real_word_export_downloads_through_existing_artifact_route(self):
        import sys, types, io, zipfile
        from xml.etree import ElementTree as ET
        station_root=Path(__file__).resolve().parents[2]/'Agent工作台'
        sys.path.insert(0,str(station_root))
        from task_station.core import Service
        from remote_gateway import RemoteGateway
        from workbench_proxy import WorkbenchProxy
        adapter=Mock();adapter.capabilities.return_value={'text_1': {'can_run':True,'mode':'test'}}
        service=Service(Path(self.temp.name)/'station',adapter)
        from backend import Bridge
        bridge=Bridge(root=Path(self.temp.name)/'room',data_dir=Path(self.temp.name)/'desktop')
        bridge._station=types.SimpleNamespace(service=service,window=None,call=lambda method,payload:{'ok':True,'data':service.call(method,payload)})
        gateway=RemoteGateway(bridge,Path(self.temp.name)/'gateway',port=0)
        self.server.workbench=WorkbenchProxy(Path(self.temp.name),Path(self.temp.name)/'uploads',transport=lambda action,payload,rid:gateway.rpc({'action':action,'payload':payload,**({'request_id':rid} if rid else {})}))
        try:
            created=gateway.rpc({'action':'task_create','payload':{'task_type':'text','role':'text_1','instruction':'测试文档'},'request_id':'word-create'})['data']
            service.call('save_text',{'id':created['id'],'text':'# 下载测试\n中文内容 & <需要保留>'})
            self.assertEqual(self.request('/api/workbench?token=paired-test&action=task_export_document&id='+created['id'])[0],400)
            body={'action':'task_export_document','payload':{'id':created['id']},'request_id':'word-export'}
            code,raw=self.request('/api/workbench?token=paired-test',body);self.assertEqual(code,200)
            data=json.loads(raw);self.assertTrue(data['ok'],data)
            name=data['data']['files'][0]['name']
            from urllib.parse import quote
            code,raw=self.request('/api/workbench-artifact?token=paired-test&id='+created['id']+'&name='+quote(name));self.assertEqual(code,200)
            self.assertEqual(raw,service.file_path(created['id'],name).read_bytes())
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                document=ET.fromstring(archive.read('word/document.xml'))
                self.assertIn('中文内容',''.join(document.itertext()))
            adapter.run.assert_not_called()
        finally:
            gateway.close();service.close()

    def test_real_excel_export_downloads_through_existing_artifact_route(self):
        import sys, types, io, zipfile
        from xml.etree import ElementTree as ET
        station_root=Path(__file__).resolve().parents[2]/'Agent工作台'
        sys.path.insert(0,str(station_root))
        from task_station.core import Service
        from remote_gateway import RemoteGateway
        from workbench_proxy import WorkbenchProxy
        adapter=Mock();adapter.capabilities.return_value={'text_1': {'can_run':True,'mode':'test'}}
        service=Service(Path(self.temp.name)/'station',adapter)
        from backend import Bridge
        bridge=Bridge(root=Path(self.temp.name)/'room',data_dir=Path(self.temp.name)/'desktop')
        bridge._station=types.SimpleNamespace(service=service,window=None,call=lambda method,payload:{'ok':True,'data':service.call(method,payload)})
        gateway=RemoteGateway(bridge,Path(self.temp.name)/'gateway',port=0)
        self.server.workbench=WorkbenchProxy(Path(self.temp.name),Path(self.temp.name)/'uploads',transport=lambda action,payload,rid:gateway.rpc({'action':action,'payload':payload,**({'request_id':rid} if rid else {})}))
        try:
            created=gateway.rpc({'action':'task_create','payload':{'task_type':'xlsx','role':'text_1','instruction':'测试表格'},'request_id':'excel-create'})['data']
            service.call('save_text',{'id':created['id'],"text":json.dumps({'version':1,'sheets':[{'name':'预算','columns':['项目','金额'],'rows':[['材料',25],['合计',{'formula':'=SUM(B2:B2)'}]]}]},ensure_ascii=False)})
            self.assertEqual(self.request('/api/workbench?token=paired-test&action=task_export_spreadsheet&id='+created['id'])[0],400)
            body={'action':'task_export_spreadsheet','payload':{'id':created['id']},'request_id':'excel-export'}
            code,raw=self.request('/api/workbench?token=paired-test',body);self.assertEqual(code,200)
            data=json.loads(raw);self.assertTrue(data['ok'],data)
            name=data['data']['files'][0]['name']
            from urllib.parse import quote
            code,raw=self.request('/api/workbench-artifact?token=paired-test&id='+created['id']+'&name='+quote(name));self.assertEqual(code,200)
            self.assertEqual(raw,service.file_path(created['id'],name).read_bytes())
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                document=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                self.assertIn('材料',''.join(document.itertext()))
                self.assertIn('SUM(B2:B2)',''.join(document.itertext()))
            adapter.run.assert_not_called()
        finally:
            gateway.close();service.close()

    def test_workbench_preview_uses_authorized_artifact_without_changing_download(self):
        import base64,time
        self.proxy.call.return_value={'ok':True,'data':{'name':'report.txt','content_base64':base64.b64encode(b'preview text').decode()}}
        def convert(source,out,stop):
            (out/'document.pdf').write_bytes(b'%PDF-1.4 static')
            (out/'page-1.png').write_bytes(bytes.fromhex('89504e470d0a1a0a')+b'fake')
            return {'pages':1}
        self.server.previews.converter=convert
        body={'id':'a'*32,'name':'report.txt'}
        self.assertEqual(self.request('/api/workbench-preview',body)[0],403)
        self.assertEqual(self.request('/api/workbench-preview?token=paired-test',body,{'Origin':'https://attacker.example'})[0],403)
        self.assertEqual(self.request('/api/workbench-preview?token=paired-test',{**body,'path':'secret'})[0],400)
        code,raw=self.request('/api/workbench-preview?token=paired-test',body);self.assertIn(code,(200,202));receipt=json.loads(raw)
        self.proxy.call.assert_called_with('task_artifact',body)
        until=time.monotonic()+3
        while self.server.previews.get(receipt['id'])['status']!='ready' and time.monotonic()<until:time.sleep(.02)
        self.assertEqual(self.request('/preview/'+receipt['id']+'/document.pdf?token=paired-test')[1][:4],b'%PDF')
        self.assertEqual(self.request('/api/workbench-artifact?token=paired-test&id='+'a'*32+'&name=report.txt')[1],b'preview text')

    def test_page_requires_pairing_and_has_existing_session_link(self):
        self.assertEqual(self.request('/collaboration')[0], 403)
        code, raw = self.request('/collaboration?token=paired-test')
        self.assertEqual(code, 200)
        self.assertIn('远程协作', raw.decode())

    def test_download_is_exact_gateway_artifact(self):
        self.proxy.call.return_value = {'ok': True, 'data': {'name': 'result.txt', 'content_base64': 'aGVsbG8='}}
        code, raw = self.request('/api/workbench-artifact?token=paired-test&id='+'a'*32+'&name=result.txt')
        self.assertEqual((code, raw), (200, b'hello'))
        self.proxy.call.assert_called_with('task_artifact', {'id': 'a'*32, 'name': 'result.txt'})

    def test_mobile_console_routes_and_assets_require_original_pairing(self):
        for path in ('/mobile',):
            self.assertEqual(self.request(path)[0],403)
            code,raw=self.request(path+'?token=paired-test')
            self.assertEqual(code,200)
        for path in ('/', '/mobile'):
            code,raw=self.request(path+'?token=paired-test')
            self.assertIn('id="mobile-controller-script"',raw.decode())
        for path in ('/mobile-controller.js','/mobile-controller.css'):
            self.assertEqual(self.request(path)[0],403)
            self.assertEqual(self.request(path+'?token=paired-test')[0],404)
        self.assertIn('远程会话台',self.request('/sessions?token=paired-test')[1].decode())
        self.assertNotIn('mobile-controller.css',self.request('/?token=paired-test&desktop_embed=1')[1].decode())

    def test_embedded_pages_have_authenticated_navigation_adapter(self):
        self.assertEqual(self.request('/desktop-embed.js')[0],403)
        for path in ('/','/collaboration','/transfer'):
            code,raw=self.request(path+'?token=paired-test&desktop_embed=1')
            self.assertEqual(code,200)
            self.assertTrue('/desktop-embed.js?token=paired-test' in raw.decode())
        self.assertFalse('desktop-embed.js' in self.request('/?token=paired-test')[1].decode())


if __name__ == '__main__':
    unittest.main()
