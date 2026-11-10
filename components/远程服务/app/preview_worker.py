"""One isolated conversion. Public output is a static, rasterized PDF and PNG pages."""
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
from uuid import uuid4
import zipfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

MAX_BYTES=100*1024*1024
Image.MAX_IMAGE_PIXELS=40_000_000


class ConversionError(Exception):pass


def office_package(source):
    try:
        with zipfile.ZipFile(source) as archive:
            entries=archive.infolist()
            if len(entries)>10000 or sum(x.file_size for x in entries)>250*1024*1024:
                raise ConversionError('文档解压后过大，请下载原文件查看。')
            for entry in entries:
                if entry.file_size>100*1024*1024:raise ConversionError('文档内含过大的内容，暂不能预览。')
                if 'vbaproject' in entry.filename.lower() or entry.filename.startswith(('Basic/','Scripts/')):
                    raise ConversionError('含宏的文档暂不转换，请下载原文件查看。')
                if entry.filename.endswith('.rels'):
                    for rel in ET.fromstring(archive.read(entry)):
                        if rel.get('TargetMode')=='External' and not rel.get('Type','').endswith('/hyperlink'):
                            raise ConversionError('文档包含外部内容引用，暂不能生成独立预览。')
                if entry.filename=='content.xml':
                    for element in ET.fromstring(archive.read(entry)).iter():
                        if element.tag.rsplit('}',1)[-1] in ('image','object','object-ole'):
                            href=element.get('{http://www.w3.org/1999/xlink}href','')
                            if ':' in href or href.startswith(('/','../')):
                                raise ConversionError('文档包含外部内容引用，暂不能生成独立预览。')
    except (zipfile.BadZipFile,ET.ParseError):raise ConversionError('文档格式损坏，无法生成PDF预览。')


def find_filee():
    # Only the installed app's fixed CLI; never a command supplied by a file.
    roots=[Path(os.environ.get('ProgramFiles','C:/Program Files'))]
    for root in roots:
        candidate=root/'Filee/filee-cli.exe'
        if candidate.is_file() and not candidate.is_symlink():return candidate
    return None


def filee_pdf(source,out,exe):
    folder=out/'filee-output';folder.mkdir()
    result=subprocess.run([str(exe),'convert',str(source),'--to','pdf','--output',str(folder),'--json','--skip'],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    stdout=result.stdout.decode('utf-8-sig',errors='replace');stderr=result.stderr.decode('utf-8-sig',errors='replace')
    try:receipt=json.loads(stdout)
    except ValueError:receipt={}
    pdf=folder/(source.stem+'.pdf')
    valid=(result.returncode==0 and isinstance(receipt,dict) and type(receipt.get('converted')) is int and receipt['converted']==1 and receipt.get('failed')==0
           and pdf.is_file() and not pdf.is_symlink() and pdf.resolve().parent==folder.resolve() and 0<pdf.stat().st_size<=MAX_BYTES)
    if valid:
        with pdf.open('rb') as stream:valid=stream.read(5)==b'%PDF-'
    if not valid:
        (out/'filee-diagnostic.json').write_text(json.dumps({'exit':result.returncode,'stdout':stdout[:4000],'stderr':stderr[:4000]}),encoding='utf-8')
        raise ConversionError('Filee未能生成有效PDF，请下载PPTX原文件查看。')
    target=out/'office-source.pdf';shutil.copyfile(pdf,target)
    return target


def office_pdf(source,out):
    office_package(source)
    filee=find_filee() if source.suffix.lower()=='.pptx' else None
    if filee:return filee_pdf(source,out,filee)
    exe=Path(__file__).resolve().parent.parent/'tools/LibreOffice/program/soffice.com'
    if not exe.is_file():raise ConversionError('Office文档转换组件不可用，请下载原文件。')
    # Use a short local temporary path, outside protected Documents folders.
    # Each job inherits its parent ACL instead of mkdtemp's owner-only ACL.
    base=Path.home()/'AppData/Local/Temp/AgentWorkbenchPreview'
    if base.is_symlink() or base.is_junction():raise ConversionError('预览临时目录无效。')
    try:
        base.mkdir(parents=True,exist_ok=True)
        # Inherit the application's ACL. mkdtemp uses mode 0700 on Windows,
        # which strips the group rights needed by restricted native helpers.
        short=base/('awb-'+uuid4().hex[:12])
        short.mkdir(mode=0o777)
        short=short.resolve()
    except OSError:
        raise ConversionError('预览临时目录不可写，请检查接收服务运行权限；原文件不受影响。') from None
    if short.parent!=base.resolve() or not short.name.startswith('awb-'):
        raise ConversionError('转换临时目录不可用。')
    try:
        return _office_pdf_short(source,out,exe,short)
    finally:
        # LibreOffice creates extension registries beyond legacy MAX_PATH. Use
        # long-path deletion only after verifying this exact per-job directory.
        try:
            if short.parent!=base.resolve() or short.is_symlink() or short.is_junction():
                raise OSError('unsafe temporary directory')
            removal=(chr(92)*2+'?'+chr(92)+str(short)) if os.name=='nt' else str(short)
            shutil.rmtree(removal)
        except OSError:
            # A cleanup warning must not turn a completed PDF into a failure.
            (out/'cleanup-diagnostic.json').write_text(json.dumps({'temporary_profile_cleanup_failed':True}),encoding='utf-8')


def _office_pdf_short(source,out,exe,short):
    staged=short/('source'+source.suffix.lower());shutil.copyfile(source,staged)
    profile=short/'profile';profile.mkdir()
    (profile/'user').mkdir()
    (profile/'user/registrymodifications.xcu').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
</oor:items>''',encoding='utf-8')
    staging=short/'output';staging.mkdir()
    result=subprocess.run([str(exe),'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo',
                           '--nodefault','--norestore','--convert-to','pdf','--outdir',str(staging),str(staged)],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=140,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=staging/(staged.stem+'.pdf')
    if result.returncode or not output.is_file():
        diagnostic={'exit':result.returncode,'stdout':getattr(result,'stdout',b'').decode('utf-8',errors='replace')[:4000],
                    'stderr':getattr(result,'stderr',b'').decode('utf-8',errors='replace')[:4000]}
        (out/'conversion-diagnostic.json').write_text(json.dumps(diagnostic),encoding='utf-8')
        if result.returncode==77 or any(word in diagnostic['stderr'].lower() for word in ('insufficient permissions','访问权限','user installation')):
            raise ConversionError('PDF预览转换器无法初始化临时配置目录，属于运行权限问题；原文件不受影响，请返回成果列表重新预览。')
        raise ConversionError('文档转换未完成，可能受密码或格式限制；请下载原文件。')
    target=out/'office-source.pdf';shutil.copyfile(output,target)
    return target


def image_pdf(source,out):
    target=out/'source-image.pdf'
    pdf=canvas.Canvas(str(target))
    with Image.open(source) as original:
        frames=getattr(original,'n_frames',1)
        if frames>100:raise ConversionError('图片超过100页，请下载原文件。')
        if frames>1 and original.format!='TIFF':
            raise ConversionError('动画图片暂不转换为静态PDF，请下载原文件。')
        for number in range(frames):
            original.seek(number)
            if original.width*original.height>40_000_000:raise ConversionError('图片尺寸过大，请下载原文件查看。')
            image=ImageOps.exif_transpose(original)
            image.thumbnail((4000,4000))
            rgba=image.convert('RGBA');image=Image.new('RGB',rgba.size,'white');image.paste(rgba,mask=rgba.getchannel('A'))
            width,height=image.size
            page_width=595;page_height=max(72,min(1600,595*height/width))
            scale=min(page_width/width,page_height/height)
            pdf.setPageSize((page_width,page_height))
            pdf.drawImage(ImageReader(image),(page_width-width*scale)/2,(page_height-height*scale)/2,width*scale,height*scale)
            pdf.showPage()
    pdf.save();return target


def text_pdf(source,out):
    raw=source.read_bytes()
    if len(raw)>2*1024*1024:raise ConversionError('文本过长，请下载原文件查看。')
    try:body=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError:raise ConversionError('文本编码暂不支持，请下载原文件。')
    if len(body)>200000:raise ConversionError('文本超过预览长度限制，请下载原文件。')
    font=next((p for p in [Path('C:/Windows/Fonts/msyh.ttc'),Path('C:/Windows/Fonts/simsun.ttc')] if p.is_file()),None)
    if not font:raise ConversionError('中文预览字体不可用，请下载原文件。')
    pdfmetrics.registerFont(TTFont('PreviewCJK',str(font),subfontIndex=0))
    target=out/'source-text.pdf';pdf=canvas.Canvas(str(target),pagesize=(595,842));pdf.setFont('PreviewCJK',10)
    y=802;pages=1
    for line in body.replace('\r\n','\n').replace('\r','\n').expandtabs(4).split('\n'):
        chunks=[];current='';width=0
        for char in line:
            char_width=pdfmetrics.stringWidth(char,'PreviewCJK',10)
            if width+char_width>515:chunks.append(current);current='';width=0
            current+=char;width+=char_width
        chunks.append(current)
        for chunk in chunks:
            if y<40:
                pdf.showPage();pdf.setFont('PreviewCJK',10);y=802;pages+=1
                if pages>100:raise ConversionError('文本超过100页，请下载原文件。')
            pdf.drawString(40,y,chunk);y-=15
    pdf.showPage();pdf.save();return target


def convert(source,out):
    extension=source.suffix.lower()
    if extension=='.pdf':pdf=source
    elif extension=='.xlsx':
        office_package(source)
        from xlsx_preview import xlsx_data_pdf
        try:pdf=xlsx_data_pdf(source,out)
        except (ValueError,KeyError,zipfile.BadZipFile,ET.ParseError) as error:
            raise ConversionError(str(error) if isinstance(error,ValueError) else '表格数据无法读取，请下载原文件。') from None
    elif extension in {'.docx','.pptx','.odt','.odp','.ods'}:pdf=office_pdf(source,out)
    elif extension in {'.png','.jpg','.jpeg','.webp','.bmp','.gif','.tif','.tiff'}:pdf=image_pdf(source,out)
    else:pdf=text_pdf(source,out)
    if pdf.stat().st_size>MAX_BYTES:raise ConversionError('转换后的PDF超过100MB，暂不能预览。')
    reader=PdfReader(str(pdf))
    if reader.is_encrypted:raise ConversionError('加密PDF暂不预览，请下载原文件。')
    pages=len(reader.pages)
    if not 1<=pages<=100:raise ConversionError('PDF预览最多支持100页，请下载原文件查看完整内容。')
    poppler=Path(os.environ.get('PDFTOPPM_PATH') or shutil.which('pdftoppm') or 'pdftoppm.exe')
    if not poppler.is_file():raise ConversionError('PDF页面转换组件不可用，请下载原文件。')
    final=out/'document.pdf';output=canvas.Canvas(str(final),pageCompression=1)
    total=0
    for number in range(1,pages+1):
        prefix=out/f'page-{number}'
        result=subprocess.run([str(poppler),'-f',str(number),'-l',str(number),'-singlefile','-cropbox','-r','120',
                               '-scale-to','2000','-png',str(pdf),str(prefix)],stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        image_path=prefix.with_suffix('.png')
        if result.returncode or not image_path.is_file():raise ConversionError('PDF页面生成失败，请下载原文件。')
        total+=image_path.stat().st_size
        if total>200*1024*1024:raise ConversionError('预览页面总大小过大，请下载原文件。')
        with Image.open(image_path) as image:
            width,height=image.size;page_size=(width*72/120,height*72/120)
            output.setPageSize(page_size);output.drawImage(ImageReader(image),0,0,*page_size)
            output.showPage()
    output.save()
    if final.stat().st_size>MAX_BYTES:raise ConversionError('静态PDF预览超过100MB，请下载原文件。')
    check=PdfReader(str(final))
    if len(check.pages)!=pages or check.get_fields():raise ConversionError('静态PDF校验失败，请下载原文件。')
    # Each page contains only the rendered image, without source forms, scripts,
    # attachments or links. The editable original remains untouched.
    return {'pages':pages}


if __name__=='__main__':
    try:print(json.dumps(convert(Path(sys.argv[1]),Path(sys.argv[2]))))
    except Exception as error:
        message=str(error) if isinstance(error,ConversionError) else '文件内容无法转换为PDF预览，请下载原文件。'
        print(json.dumps({'error':message}));sys.exit(1)
