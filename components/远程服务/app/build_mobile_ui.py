"""Inline the two maintained mobile assets for existing template-reading receivers.

Run after changing mobile-controller.js/css. No data, network or credentials.
"""
from pathlib import Path
import re
import base64
import json
import sys

BASE=Path(__file__).resolve().parent
def partner_styles():
    art=BASE/'ui-assets'/'partner-art.css'
    return art.read_text(encoding='utf-8') if art.exists() else ''

def activity_assets():
    keys=[f'{scene}.{pose}' for scene in ('home','plaza','orchard') for pose in ('front','back','sit')]+[f'room.{pose}' for pose in ('back','turn','relax','rest')]
    return {key:'data:image/png;base64,'+base64.b64encode((BASE/'ui-assets'/f'activity-{key}.png').read_bytes()).decode('ascii') for key in keys}

def build(check_only=False):
    page=BASE/'collaboration.html';html=page.read_text(encoding='utf-8')
    for kind,name,tag in [('styles','mobile-controller.css','style'),('script','mobile-controller.js','script')]:
        start=f'<!-- mobile-controller-{kind}:start -->';end=f'<!-- mobile-controller-{kind}:end -->'
        content=(BASE/name).read_text(encoding='utf-8')
        if kind=='styles':content=partner_styles()+'\n'+(BASE/'mobile-room.css').read_text(encoding='utf-8')+'\n'+content+'\n'+(BASE/'partner-theme.css').read_text(encoding='utf-8')
        if kind=='script':content=(BASE/'mobile-room.js').read_text(encoding='utf-8').replace('__PET_ACTIVITY_ASSETS__',json.dumps(activity_assets(),ensure_ascii=True,separators=(',',':'))).replace('__ROOM_PREVIEW_DATA__','data:image/png;base64,'+base64.b64encode((BASE/'ui-assets/room-preview.png').read_bytes()).decode('ascii'))+'\n'+(BASE/'partner-theme.js').read_text(encoding='utf-8')+'\n'+(BASE/'keyword-router.js').read_text(encoding='utf-8')+'\n'+(BASE/'pc_file_search.js').read_text(encoding='utf-8')+'\n'+content
        assert '</'+tag not in content.lower()
        block=start+f'\n<{tag} id="mobile-controller-{kind}">\n'+content+f'\n</{tag}>\n'+end
        if start in html:
            html=re.sub(re.escape(start)+r'.*?'+re.escape(end),lambda _:block,html,flags=re.S)
        else:html=html.replace('</head>',block+'\n</head>',1)
    if not check_only:page.write_text(html,encoding='utf-8')
    page=BASE/'mobile_bot.html';html=page.read_text(encoding='utf-8')
    content=(BASE/'partner-theme.js').read_text(encoding='utf-8')+'\n'+(BASE/'session_actions.js').read_text(encoding='utf-8')+'\n'+(BASE/'coding_actions.js').read_text(encoding='utf-8')+'\n'+(BASE/'conversation_tools.js').read_text(encoding='utf-8')
    assert '</script' not in content.lower()
    block='<!-- session-actions:start -->\n<script id="session-actions-script">\n'+content+'\n</script>\n<!-- session-actions:end -->'
    html=re.sub(r'<!-- session-actions:start -->.*?<!-- session-actions:end -->',lambda _:block,html,flags=re.S)
    styles='<!-- partner-theme:start -->\n<style>\n'+partner_styles()+'\n'+(BASE/'partner-theme.css').read_text(encoding='utf-8')+'\n</style>\n<!-- partner-theme:end -->'
    if '<!-- partner-theme:start -->' in html:
        html=re.sub(r'<!-- partner-theme:start -->.*?<!-- partner-theme:end -->',lambda _:styles,html,flags=re.S)
    else:html=html.replace('</head>',styles+'\n</head>',1)
    if not check_only:page.write_text(html,encoding='utf-8')
    print('Mobile assets verified' if check_only else 'Mobile assets inlined; no dependency on a new static asset route')
if __name__=='__main__':build(check_only='--check' in sys.argv)
