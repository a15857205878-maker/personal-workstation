"""Bounded XLSX data-to-PDF view; reads cached values without executing formulas."""
from pathlib import Path
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, TableStyle, PageBreak, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

def xlsx_data_pdf(source,out):
    font=next((p for p in [Path('C:/Windows/Fonts/msyh.ttc'),Path('C:/Windows/Fonts/simsun.ttc')] if p.is_file()),None)
    if not font:raise ValueError('中文预览字体不可用，请下载原文件。')
    pdfmetrics.registerFont(TTFont('XlsxPreviewCJK',str(font),subfontIndex=0))
    style=ParagraphStyle('cell',fontName='XlsxPreviewCJK',fontSize=9,leading=13,wordWrap='CJK')
    heading=ParagraphStyle('heading',parent=style,fontSize=13,leading=20,spaceAfter=8)
    note=ParagraphStyle('note',parent=style,fontSize=8,leading=12,textColor=colors.HexColor('#526579'),spaceAfter=9)
    def paragraph(value,kind=style):return Paragraph(escape(str(value)).replace('\n','<br/>'),kind)
    story=[];total=0
    with zipfile.ZipFile(source) as archive:
        def xml(name):
            if archive.getinfo(name).file_size>8*1024*1024:raise ValueError('工作表过大，请下载原文件查看。')
            return ET.fromstring(archive.read(name))
        workbook=xml('xl/workbook.xml');relations={r.get('Id'):r for r in xml('xl/_rels/workbook.xml.rels')}
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(si.itertext()) for si in xml('xl/sharedStrings.xml').findall('x:si',NS)]
            if len(shared)>20000:raise ValueError('工作簿文字项过多，请下载原文件查看。')
        sheets=workbook.findall('x:sheets/x:sheet',NS)
        if not 1<=len(sheets)<=8:raise ValueError('基础预览最多支持8个工作表，请下载原文件。')
        for sheet in sheets:
            relation=relations.get(sheet.get(REL))
            if relation is None or relation.get('TargetMode')=='External':raise ValueError('工作表引用无效。')
            target=relation.get('Target','')
            name=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if not name.startswith('xl/worksheets/') or name not in archive.namelist():raise ValueError('工作表位置无效。')
            cells={};maxrow=maxcol=0
            for cell in xml(name).findall('x:sheetData/x:row/x:c',NS):
                ref=cell.get('r','');match=re.fullmatch('([A-Z]{1,2})([1-9][0-9]{0,3})',ref)
                if not match:raise ValueError('单元格位置无效，请下载原文件。')
                column=0
                for char in match[1]:column=column*26+ord(char)-64
                row=int(match[2]);total+=1
                if column>20 or row>2000 or total>10000:raise ValueError('基础预览最多20列、2000行、10000个单元格，请下载完整文件。')
                if (row,column) in cells:raise ValueError('工作表存在重复单元格位置。')
                kind=cell.get('t','');value=cell.findtext('x:v',default='',namespaces=NS)
                if kind=='inlineStr':value=''.join(t.text or '' for t in cell.findall('x:is//x:t',NS))
                elif kind=='s':
                    if not value.isdigit() or int(value)>=len(shared):raise ValueError('共享文字引用无效。')
                    value=shared[int(value)]
                elif kind=='b':value='TRUE' if value=='1' else 'FALSE'
                if cell.find('x:f',NS) is not None and not value:value='〔公式未缓存结果〕'
                if len(value)>4000:raise ValueError('单元格文字过长，请下载原文件。')
                cells[row,column]=value;maxrow=max(maxrow,row);maxcol=max(maxcol,column)
            if not cells:
                if story:story.append(PageBreak())
                story.extend([paragraph(sheet.get('name','工作表'),heading),paragraph('空工作表。')]);continue
            for first in range(1,maxcol+1,6):
                if story:story.append(PageBreak())
                last=min(first+5,maxcol)
                story.append(paragraph(sheet.get('name','工作表')+f' · 第{first}–{last}列',heading))
                story.append(paragraph('基础数据预览：公式显示文件保存的结果，不重新计算；日期格式、合并单元格、图表及完整排版请下载原件查看。',note))
                data=[[paragraph(str(r)),*[paragraph(cells.get((r,c),'')) for c in range(first,last+1)]] for r in range(1,maxrow+1)]
                table=LongTable(data,colWidths=[28]+[730/(last-first+1)]*(last-first+1),repeatRows=1,splitByRow=1,splitInRow=1)
                table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8F0F8')),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#B6C8DB')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DFE6EE')),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                story.append(table)
    target=out/'source-xlsx.pdf'
    def footer(canvas,doc):
        if doc.page>100:raise ValueError('预览超过100页，请下载原文件。')
        canvas.setFont('XlsxPreviewCJK',8);canvas.setFillColor(colors.HexColor('#526579'));canvas.drawString(28,17,'基础表格数据视图 · 原文件保留完整功能');canvas.drawRightString(814,17,str(doc.page))
    SimpleDocTemplate(str(target),pagesize=(842,595),leftMargin=28,rightMargin=28,topMargin=24,bottomMargin=32).build(story,onFirstPage=footer,onLaterPages=footer)
    return target
