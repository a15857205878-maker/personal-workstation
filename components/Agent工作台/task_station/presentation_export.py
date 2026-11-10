"""Small editable 16:9 PPTX decks from bounded JSON; standard library only."""
import json,re,zipfile,unicodedata
from io import BytesIO
from xml.sax.saxutils import escape

CONTRACT='只返回一个JSON对象，不写代码、链接或席位格式。使用version=2协议：{"version":2,"title":"演示标题","slides":[{"layout":"image_left","palette":"spring","title":"页面标题","subtitle":"简短说明","bullets":["要点一","要点二"],"image_id":"从可用配图清单选择的ID"}]}。顶层仅version/title/slides。1至12页；title最多60字、每页title最多30字、subtitle最多100字；字段不得含换行/制表符，总文字最多8000字。layout可选cover（封面，最多2条、每条30字，配图可选）、image_left（左图右文，须image_id，最多4条、每条40字）、cards（要点卡片，最多4条、每条65字，不含image_id）。palette可选blue/spring/autumn。没有图片的页面省略image_id。只能引用宿主提供的图片ID，禁止URL或本地路径；需要图片却无可用配图时明确回复缺少图片，不用占位框冒充。宿主嵌入实际图片、保持文字可编辑，并提供固定配色版式，不支持动画或图表。当前模型只收到配图名称/尺寸，无法查看图片像素；审查仅核对结构与内容，不声称完成视觉验收。旧version=1文字页仍兼容，但有配图时必须version=2并使用全部配图。'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
INVALID=re.compile(r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')

def text(value,limit,empty=False):
 if not isinstance(value,str) or len(value)>limit or INVALID.search(value) or any(c in value for c in '\r\n\t') or (not empty and not value.strip()):raise ValueError('PPTX文字为空、过长或包含无效字符')
 return value

def parse(raw):
 if not isinstance(raw,str) or len(raw)>20000:raise ValueError('PPTX结构超过20000字符上限')
 raw=raw.strip()
 if raw.startswith('```json\n') and raw.endswith('```'):raw=raw[8:-3].strip()
 try:value=json.loads(raw)
 except (ValueError,RecursionError):raise ValueError('需要完整PPTX结构JSON，文字大纲不能当作文件') from None
 if not isinstance(value,dict) or set(value)!={'version','title','slides'} or type(value['version']) is not int or value['version'] not in (1,2):raise ValueError('PPTX须包含version=1或2、title和slides')
 text(value['title'],60)
 if not isinstance(value['slides'],list) or not 1<=len(value['slides'])<=12:raise ValueError('PPTX须为1至12页')
 count=len(value['title'])
 for slide in value['slides']:
  if not isinstance(slide,dict):raise ValueError('页面结构无效')
  base={'title','subtitle','bullets'}
  if value['version']==1:
   if set(slide)!=base:raise ValueError('每页须包含title、subtitle和bullets')
  else:
   required=base|{'layout','palette'}
   if not required<=set(slide) or set(slide)-required-{'image_id'}:raise ValueError('图文页字段无效')
   if slide['layout'] not in ('cover','image_left','cards') or slide['palette'] not in ('blue','spring','autumn'):raise ValueError('版式或配色不支持')
   if 'image_id' in slide and (not isinstance(slide['image_id'],str) or not re.fullmatch('[a-f0-9]{32}',slide['image_id'])):raise ValueError('只能引用已上传配图ID')
   if slide['layout']=='image_left' and 'image_id' not in slide:raise ValueError('图文页缺少配图，请添加图片')
   if slide['layout']=='cards' and 'image_id' in slide:raise ValueError('卡片版式不含图片')
  text(slide['title'],30);text(slide['subtitle'],100,True)
  if not isinstance(slide['bullets'],list) or len(slide['bullets'])>6:raise ValueError('每页最多6条要点')
  limit=65
  if value['version']==2:
   max_items,limit={'cover':(2,30),'image_left':(4,40),'cards':(4,65)}[slide['layout']]
   if len(slide['bullets'])>max_items:raise ValueError('当前版式要点过多')
  for bullet in slide['bullets']:text(bullet,limit)
  count+=len(slide['title'])+len(slide['subtitle'])+sum(map(len,slide['bullets']))
 if count>8000:raise ValueError('PPTX总文字最多8000字')
 return value

def wrapped(value,width):
 lines=[];line='';units=0
 for c in value:
  n=2 if unicodedata.east_asian_width(c) in ('W','F') else 1
  if c=='\n' or units+n>width:
   lines.append(line);line='';units=0
   if c=='\n':continue
  line+=c;units+=n
 lines.append(line);return lines

def paragraphs(value,size,color,bold=False,width=84):
 result=[]
 for line in wrapped(value,width):
  result.append('<a:p><a:pPr><a:lnSpc><a:spcPct val="115000"/></a:lnSpc><a:buNone/></a:pPr><a:r><a:rPr lang="zh-CN" sz="'+str(size)+'" b="'+('1' if bold else '0')+'"><a:solidFill><a:srgbClr val="'+color+'"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>'+escape(line)+'</a:t></a:r><a:endParaRPr lang="zh-CN" sz="'+str(size)+'"/></a:p>')
 return ''.join(result)

def shape(number,name,x,y,w,h,body):
 return f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="square" lIns="0" rIns="0" tIns="0" bIns="0"/><a:lstStyle/>{body}</p:txBody></p:sp>'

GROUP='<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'

def relationships(items):
 return '<Relationships xmlns="'+REL+'">'+''.join(f'<Relationship Id="{rid}" Type="{R}/{kind}" Target="{target}"/>' for rid,kind,target in items)+'</Relationships>'

def theme():
 colors=''.join(f'<a:{key}><a:srgbClr val="{value}"/></a:{key}>' for key,value in [('dk1','25374F'),('lt1','FFFFFF'),('dk2','49617F'),('lt2','EDF3F9'),('accent1','397CDB'),('accent2','48A899'),('accent3','E8B14E'),('accent4','8C80C8'),('accent5','DF8475'),('accent6','71A8D8'),('hlink','2863B4'),('folHlink','7757A4')])
 font='<a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface="Arial"/>'
 fill='<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
 line='<a:ln w="12700">'+fill+'<a:prstDash val="solid"/></a:ln>'
 return f'<a:theme xmlns:a="{A}" name="Workstation"><a:themeElements><a:clrScheme name="Blue White">{colors}</a:clrScheme><a:fontScheme name="Workstation"><a:majorFont>{font}</a:majorFont><a:minorFont>{font}</a:minorFont></a:fontScheme><a:fmtScheme name="Workstation"><a:fillStyleLst>{fill*3}</a:fillStyleLst><a:lnStyleLst>{line*3}</a:lnStyleLst><a:effectStyleLst>'+('<a:effectStyle><a:effectLst/></a:effectStyle>'*3)+f'</a:effectStyleLst><a:bgFillStyleLst>{fill*3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>'

PALETTES={'blue':('F3F7FD','25374F','397CDB','FFFFFF'),'spring':('F3F8EF','264639','5B936C','FFFFFF'),'autumn':('FBF4EA','563D2B','B86D39','FFFFFF')}

def panel(number,x,y,w,h,color):
 return f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="Panel"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>'

def picture(asset,x,y,w,h):
 scale=min(w/asset['width'],h/asset['height']);iw=round(asset['width']*scale);ih=round(asset['height']*scale);x+=(w-iw)//2;y+=(h-ih)//2
 return f'<p:pic><p:nvPicPr><p:cNvPr id="40" name="Embedded photo"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{iw}" cy="{ih}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'

def render_v2(slide,asset):
 bg,ink,accent,card=PALETTES[slide['palette']];layout=slide['layout']
 body=panel(20,640000,350000,680000,70000,accent)
 body+=shape(2,'Title',640000,610000,10900000,850000,paragraphs(slide['title'],2800,ink,True,60))
 body+=shape(3,'Subtitle',640000,1450000,10900000,760000,paragraphs(slide['subtitle'],1400,accent,width=100))
 if layout=='cards':
  for j,bullet in enumerate(slide['bullets']):
   x=640000+(j%2)*5620000;y=2430000+(j//2)*1700000
   body+=panel(21+j,x,y,5300000,1470000,card)
   body+=shape(10+j,'Editable card',x+240000,y+230000,4820000,1100000,paragraphs(bullet,1700,ink,width=42))
 else:
  if asset:
   body+=panel(21,640000,2430000,5700000,3600000,card)+picture(asset,760000,2550000,5460000,3360000)
  x=6720000 if asset else 1000000;w=4800000 if asset else 10200000;width=40 if asset else 84
  for j,bullet in enumerate(slide['bullets']):
   body+=shape(10+j,'Editable point',x,2500000+j*870000,w,800000,paragraphs('• '+bullet,1800,ink,width=width))
 return bg,body

def presentation_bytes(raw,assets=None):
 value=parse(raw);slides=value['slides'];parts={};assets=assets or {}
 used={slide.get('image_id') for slide in slides if slide.get('image_id')}
 if used-set(assets):raise ValueError('页面引用的图片不可用，请添加实际配图')
 if assets and (value['version']!=2 or set(assets)-used):raise ValueError('请用version=2引用全部已添加配图，不能退回纯文字页')
 for asset in assets.values():
  if asset.get('extension') not in ('png','jpg') or not isinstance(asset.get('data'),bytes) or len(asset['data'])>4*1024*1024 or not all(type(asset.get(k)) is int and 0<asset[k]<=1600 for k in ('width','height')):raise ValueError('配图结构无效')
 parts['_rels/.rels']=relationships([('rId1','officeDocument','ppt/presentation.xml')])
 ids=''.join(f'<p:sldId id="{255+i}" r:id="rId{i+1}"/>' for i in range(1,len(slides)+1))
 parts['ppt/presentation.xml']=f'<p:presentation xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{ids}</p:sldIdLst><p:sldSz cx="12192000" cy="6858000" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
 parts['ppt/_rels/presentation.xml.rels']=relationships([('rId1','slideMaster','slideMasters/slideMaster1.xml')]+[(f'rId{i+1}','slide',f'slides/slide{i}.xml') for i in range(1,len(slides)+1)])
 mapping='accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"'
 parts['ppt/slideMasters/slideMaster1.xml']=f'<p:sldMaster xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}"><p:cSld><p:spTree>{GROUP}</p:spTree></p:cSld><p:clrMap {mapping}/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>'
 parts['ppt/slideMasters/_rels/slideMaster1.xml.rels']=relationships([('rId1','slideLayout','../slideLayouts/slideLayout1.xml'),('rId2','theme','../theme/theme1.xml')])
 parts['ppt/slideLayouts/slideLayout1.xml']=f'<p:sldLayout xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>{GROUP}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
 parts['ppt/slideLayouts/_rels/slideLayout1.xml.rels']=relationships([('rId1','slideMaster','../slideMasters/slideMaster1.xml')]);parts['ppt/theme/theme1.xml']=theme()
 for i,slide in enumerate(slides,1):
  body=shape(2,'Title',640000,450000,10900000,560000,paragraphs(slide['title'],2600,'25374F',True,60))
  body+=shape(3,'Subtitle',640000,1150000,10900000,700000,paragraphs(slide['subtitle'],1500,'647A92',width=100))
  bullet=''.join(paragraphs('• '+v,1800,'25374F',width=84)+'<a:p><a:endParaRPr sz="600"/></a:p>' for v in slide['bullets'])
  body+=shape(4,'Editable content',640000,2080000,10900000,4200000,bullet or paragraphs('',1800,'25374F'))
  bg='F7FAFF'
  if value['version']==2:bg,body=render_v2(slide,assets.get(slide.get('image_id')))
  body+=shape(5,'Page',640000,6400000,10900000,250000,paragraphs(str(i)+' / '+str(len(slides)),1000,'647A92'))
  parts[f'ppt/slides/slide{i}.xml']=f'<p:sld xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}"><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree>{GROUP}{body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
  rels=[('rId1','slideLayout','../slideLayouts/slideLayout1.xml')]
  if slide.get('image_id'):
   asset=assets[slide['image_id']];name=slide['image_id']+'.'+asset['extension'];parts['ppt/media/'+name]=asset['data'];rels.append(('rId2','image','../media/'+name))
  parts[f'ppt/slides/_rels/slide{i}.xml.rels']=relationships(rels)
 types={'ppt/presentation.xml':'presentation.main','ppt/slideMasters/slideMaster1.xml':'slideMaster','ppt/slideLayouts/slideLayout1.xml':'slideLayout'}
 overrides=''.join(f'<Override PartName="/{name}" ContentType="application/vnd.openxmlformats-officedocument.presentationml.{kind}+xml"/>' for name,kind in types.items())
 overrides+='<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
 overrides+=''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1,len(slides)+1))
 parts['[Content_Types].xml']='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/>'+overrides+'</Types>'
 out=BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,xml in parts.items():z.writestr(zipfile.ZipInfo(name),xml if isinstance(xml,bytes) else '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+xml,compress_type=zipfile.ZIP_DEFLATED)
 return out.getvalue()
