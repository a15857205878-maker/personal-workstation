"""Explicit public selection -> immutable local website source package."""
from html import escape
from pathlib import Path
import hashlib,json,uuid,zipfile

def export_package(root,project,entries):
    from site_materials import ordinary,fingerprint
    assets=[];public=[];total=0
    for index,entry in enumerate(entries,1):
        row={key:entry[key] for key in ('id','title','description','version','date','kind','source','excerpt')}
        ref=entry.get('_reference')
        if ref:
            path=ordinary(ref['path'])
            if fingerprint(path)['sha256']!=ref['sha256']:raise ValueError(ref['name']+' 原件已变化，请重新选入')
            total+=ref['size']
            if total>200*1024*1024:raise ValueError('素材包最多200MiB，请分批导出')
            # Snapshot bytes, not a later re-open after validation.
            with path.open('rb') as stream:raw=stream.read(ref['size']+1)
            if len(raw)!=ref['size'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('素材在导出时变化，请重试')
            name=f'media/{index:02d}'+path.suffix.lower();assets.append((name,raw));row['asset']=name;row['sha256']=ref['sha256']
        public.append(row)
    manifest={'format':'personal-site-materials','version':1,'project':{'id':project['id'],'title':project['title'],'version':project['version']},'entries':public}
    md=['# '+project['title'],'','版本：'+project['version'],'','本地网站取材包；尚未发布。','']
    cards=[]
    for index,e in enumerate(public,1):
        md.extend([f'## {index}. '+e['title'],'',e['date']+' · '+e['version'],'',e['description'],''])
        if e['source']:md.extend(['出处：'+e['source'],''])
        if e['excerpt']:md.extend(['摘录：'+e['excerpt'],''])
        media='';asset=e.get('asset','')
        if asset:
            md.extend(['素材：['+asset+']('+asset+')',''])
            if Path(asset).suffix in ('.png','.jpg','.jpeg','.gif','.webp'):media=f'<img src="{asset}" alt="{escape(e["title"],quote=True)}" loading="lazy">'
            elif Path(asset).suffix in ('.mp4','.webm'):media=f'<video src="{asset}" controls preload="metadata"></video>'
            else:media=f'<a href="{asset}" download>下载素材原件</a>'
        cards.append(f'<article><p class="eyebrow">{index:02d} · {escape(e["kind"])} · {escape(e["date"])}</p><h2>{escape(e["title"])}</h2>{media}<p>{escape(e["description"])}</p><small>{escape(e["source"])}</small><blockquote>{escape(e["excerpt"])}</blockquote></article>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; media-src \'self\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>'+escape(project['title'])+'</title><style>body{font:16px/1.7 system-ui;background:#f2f4f4;color:#203738;max-width:920px;margin:auto;padding:24px;overflow-wrap:anywhere}article{background:white;border:1px solid #d6dfdf;border-radius:18px;padding:24px;margin:20px 0}img,video{max-width:100%;max-height:540px;display:block;margin:18px auto;border-radius:12px}.eyebrow,small{color:#536d6e}p,blockquote{white-space:pre-wrap}h1{font-size:32px}blockquote{border-left:3px solid #b0c7c6;padding-left:16px;margin-left:0}</style><h1>'+escape(project['title'])+'</h1><p>版本 '+escape(project['version'])+' · 本地分镜预览 · 尚未发布</p>'+''.join(cards)+'</html>'
    identifier=uuid.uuid4().hex;folder=Path(root)/'exports'/identifier;folder.mkdir(parents=True)
    files=[('updates.md','\n'.join(md).encode('utf-8')),('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')),('storyboard.html',html.encode('utf-8'))]+assets
    # Also keep an unpacked preview: no encoder, server, upload or execution required.
    for name,raw in files:
        target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    package=folder/'website-materials.zip'
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files:archive.writestr(name,raw)
    return dict(id=identifier,path=str(package),folder=str(folder),count=len(entries),message='素材包已在本地生成，尚未发布')
