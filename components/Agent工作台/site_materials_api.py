"""Fixed desktop-only actions joining existing file owners to the materials metadata store."""
from pathlib import Path
import hashlib,threading
from site_materials import SiteMaterials

FIELDS={
    'list':set(),'create':{'title','revision'},'save':{'project','revision'},'delete':{'id','revision'},
    'add':{'id','revision'},'pick':{'id','revision'},'artifacts':set(),'search':{'query','mode'},
    'add_artifact':{'id','revision','artifact_id'},'add_library':{'id','revision','file_id'},
    'preview':{'id','entry_id'},'open':{'id','entry_id'},'export':{'id','selected','revision'},'open_export':{'id','export_id'},
}

class MaterialsAPI:
    def __init__(self,core):
        self.core=core;self.store=SiteMaterials(core.bridge._data_dir);self.lock=threading.RLock();self.search_rows={}
    def call(self,operation,payload):
        if operation not in FIELDS or set(payload)!=FIELDS[operation]:raise ValueError('网站素材台参数无效')
        c=self.core;s=self.store;p=payload
        with self.lock:
            if operation=='list':return s.listing()
            if operation=='create':return s.create(p['title'],p['revision'])
            if operation=='save':return s.save(p['project'],p['revision'])
            if operation=='delete':return s.delete(p['id'],p['revision'])
            if operation=='add':return s.add_entry(p['id'],p['revision'])
            if operation=='artifacts':return c.artifacts()
            if operation=='search':
                if p['mode'] not in ('filename','content'):raise ValueError('检索方式无效')
                c.call('workstation_file_roots',{});files=c.remote._files
                result=files.library_content(p['query']) if p['mode']=='content' else files.library_files(p['query'])
                self.search_rows={row['id']:row for row in result['files']};return result
            if operation=='add_library':
                row=self.search_rows.get(p['file_id'])
                if row is None:raise ValueError('检索结果已过期，请重新查找')
                files=c.remote._files
                # Validate ticket, revision and opened handle with the original file owner.
                with files.open_file(p['file_id']) as stream:
                    path=Path(stream.name);digest=hashlib.file_digest(stream,'sha256').hexdigest()
                if row.get('content_sha256') and row['content_sha256']!=digest:raise ValueError('正文原件已变化，请重新查找')
                return s.add_entry(p['id'],p['revision'],title=row['name'],path=path,
                                   source=row['relative']+(' · '+row['location'] if row.get('location') else ''),excerpt=row.get('excerpt',''),expected_sha256=digest)
            if operation=='add_artifact':
                path=c.artifact_browser.path(p['artifact_id'])
                return s.add_entry(p['id'],p['revision'],title=path.name,path=path,source='工作站成果 · '+path.name)
            if operation=='pick':
                # Validate project/revision before opening a native picker.
                state=s.listing()
                if p['revision']!=state['revision'] or not any(x['id']==p['id'] for x in state['projects']):raise ValueError('项目已变化，请刷新')
                if c.bridge.station_window is None:raise ValueError('请在电脑工作站选择本地素材')
                if not c._artifact_dialog.acquire(blocking=False):raise ValueError('已有文件选择窗口打开')
                try:
                    import webview
                    paths=c.bridge.station_window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=False,file_types=('网站素材 (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.mp4;*.webm;*.txt;*.md;*.pdf;*.csv;*.json;*.docx;*.xlsx;*.pptx;*.zip)',))
                    if not paths:return dict(state,cancelled=True)
                    path=Path(paths[0]);return s.add_entry(p['id'],p['revision'],title=path.stem,path=path,source='本地素材 · '+path.name)
                finally:c._artifact_dialog.release()
            if operation=='preview':return s.preview(p['id'],p['entry_id'])
            if operation=='open':return s.open_reference(p['id'],p['entry_id'],c.bridge.opener)
            if operation=='export':return s.export(p['id'],p['selected'],p['revision'])
            if operation=='open_export':return s.open_export(p['id'],p['export_id'],c.bridge.opener)
