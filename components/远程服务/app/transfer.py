"""Local Wi-Fi photo receiver. Run with Python 3.12 or newer."""
import argparse
import base64
from contextlib import closing
import ctypes
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit
from tasks import TaskManager
from adapters import agents
from bot_core import BotCore
from session_reader import CodexSessionReader
from deepseek_history import DeepSeekHistoryReader
from deepseek_resume import DeepSeekReplies
from reply_queue import ReplyQueue
from bot_tasks import create_bot_task
from conversation_view import conversation_detail
from network_access import NetworkAccess
from pairing import load_token, save_token
from desktop_open import DesktopOpenManager
from diagnostics import server_diagnostics
from usage import UsageService
from artifact_preview import PreviewService
from deepseek_balance import DeepSeekBalanceService
from file_review import FileReview
from workbench_proxy import WorkbenchProxy,artifact_action, READS

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'vendor'))
MAX_BYTES = 100 * 1024 * 1024
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.tif', '.tiff', '.avif'}


class MessageStore:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, sender TEXT NOT NULL, time REAL NOT NULL, client_id TEXT UNIQUE NOT NULL)')

    def list(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT id,text,sender,time FROM messages ORDER BY id DESC LIMIT 200').fetchall()
            return [dict(row) for row in reversed(rows)]

    def add(self, text, sender, client_id):
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError('请输入文字，每条最多 10000 字。')
        if sender not in ('phone', 'computer'):
            raise ValueError('无效的发送设备。')
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 100:
            raise ValueError('消息标识无效，请刷新页面。')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute('INSERT OR IGNORE INTO messages(text,sender,time,client_id) VALUES(?,?,?,?)', (text, sender, time.time(), client_id))
            row = db.execute('SELECT id,text,sender,time FROM messages WHERE client_id=?', (client_id,)).fetchone()
            if row['text'] != text or row['sender'] != sender:
                raise ValueError('消息标识冲突，请重新发送。')
            return dict(row)


def local_ips():
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1', 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        found.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return list(dict.fromkeys(ip for ip in found if not ip.startswith(('127.', '169.254.'))))


def create_server(host, port, folder, token):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()
    messages = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not put pairing secrets into access logs.

        def reply(self, code, data, mime='application/json; charset=utf-8'):
            # Windows may reset a closing socket with unread POST bytes before
            # the client receives our error. Drain small rejected bodies first.
            remaining = getattr(self, '_remaining_body', 0)
            if code >= 400 and 0 < remaining <= 256*1024:
                previous_timeout = self.connection.gettimeout()
                try:
                    self.connection.settimeout(2)
                    self.read_body(remaining)
                except OSError:
                    pass
                finally:
                    self.connection.settimeout(previous_timeout)
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(data)

        def authorize(self):
            self.query = parse_qs(urlsplit(self.path).query)
            provided = self.query.get('token', [''])[0]
            if not hmac.compare_digest(provided.encode('utf-8'), token.encode('utf-8')):
                self.reply(403, {'error': '配对已失效，请重新扫描电脑上的二维码。'})
                return False
            return True

        def ui_page(self,name):
            page=(BASE/name).read_text(encoding='utf-8')
            if self.query.get('desktop_embed',[''])[0]=='1':
                script='<script src="/desktop-embed.js?token='+quote(token,safe='')+'"></script>'
                page=page.replace('</head>',script+'</head>',1) if '</head>' in page else page.replace('<meta charset="utf-8">','<meta charset="utf-8">'+script,1)
            self.reply(200,page.encode('utf-8'),'text/html; charset=utf-8')

        def workbench_origin(self):
            origin = self.headers.get('Origin')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin != 'http://' + self.headers.get('Host', '')):
                self.reply(403, {'ok': False, 'error': '请从已配对的手机页面操作。'})
                return False
            return True

        def pc_files_get(self,path):
            if not self.workbench_origin():return
            headers_sent=False
            try:
                if path=='/api/pc-files/status':
                    roots=self.server.pc_files.local_roots()['roots'];self.reply(200,{'roots':[{'id':row['id'],'label':row['label']} for row in roots]});return
                if path=='/api/pc-files/library':
                    mode=self.query.get('mode',['filename'])[0]
                    if mode not in ('filename','content'):raise ValueError('检索方式无效。')
                    method=self.server.pc_files.library_content if mode=='content' else self.server.pc_files.library_files
                    self.reply(200,method(self.query.get('q',[''])[0]));return
                if path=='/api/pc-files/search':
                    self.reply(200,self.server.pc_files.search(self.query.get('q',[''])[0]));return
                if path!='/api/pc-files/download':raise ValueError('无效入口。')
                with self.server.pc_files.open_file(self.query.get('id',[''])[0]) as stream:
                    size=os.fstat(stream.fileno()).st_size
                    self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(size));self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(Path(stream.name).name,safe=''));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();headers_sent=True
                    remaining=size
                    while remaining:
                        chunk=stream.read(min(1024*1024,remaining))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):return
            except (ValueError,KeyError,OSError):
                if not headers_sent:self.reply(400,{'error':'无法取回该文件，可能已变化、过期或目录不可用；请重新查找。'})

        def workbench_get(self, path):
            if not self.workbench_origin():
                return
            try:
                if path == '/api/workbench-artifact':
                    result = self.server.workbench.call(artifact_action(self.query.get('kind',['task'])[0]), {'id': self.query.get('id', [''])[0], 'name': self.query.get('name', [''])[0]})
                    if not result.get('ok'):
                        self.reply(400, result)
                        return
                    data = result['data']
                    content = base64.b64decode(data['content_base64'], validate=True)
                    if len(content) > 10 * 1024 * 1024:
                        raise ValueError('成果超过手机单文件下载上限，请在电脑查看。')
                    name = data['name']
                    if not WorkbenchProxy._filename(name):
                        raise ValueError('成果名称无效。')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(name, safe=''))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    self.wfile.write(content)
                    return
                action = self.query.get('action', ['catalog'])[0]
                if action == 'room_status' and set(self.query) - {'action', 'token'}:
                    raise ValueError('小屋摘要不接受额外参数。')
                if action not in READS or action in ('task_artifact','collaboration_artifact'):
                    raise ValueError('此操作需要明确确认后提交。')
                payload = {'id': self.query.get('id', [''])[0]} if action in ('task_get', 'collaboration_get', 'attachment_get') else {}
                self.reply(200, self.server.workbench.call(action, payload))
            except (ValueError, KeyError, OSError):
                self.reply(400, {'ok': False, 'error': '无法读取工作台内容，请刷新记录后重试。'})

        def workbench_post(self):
            if not self.workbench_origin():
                return
            try:
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    raise ValueError('请以 JSON 格式提交。')
                value = self.read_json()
                if not isinstance(value, dict) or set(value) - {'action', 'payload', 'request_id'}:
                    raise ValueError('提交格式无效。')
                result = self.server.workbench.call(value.get('action'), value.get('payload', {}), value.get('request_id'))
                self.reply(200, result)
            except ValueError as exc:
                self.reply(400, {'ok': False, 'error': str(exc)[:500]})
            except (KeyError, OSError):
                self.reply(503, {'ok': False, 'error': '电脑连接暂不可用，请先刷新记录，未自动重复执行。'})

        def do_GET(self):
            import re
            raw_path=urlsplit(self.path).path
            if raw_path.startswith('/web-product/'):
                from urllib.parse import unquote
                from web_product import CSP
                try:
                    match=re.fullmatch(r'/web-product/([a-f0-9]{48})/(.+)',raw_path)
                    if not match:raise ValueError('无效预览地址。')
                    raw,mime=self.server.web_products.asset(match[1],unquote(match[2]))
                    self.send_response(200)
                    for key,value in [('Content-Type',mime),('Content-Length',str(len(raw))),('Content-Security-Policy',CSP),('Cache-Control','no-store'),('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff'),('Access-Control-Allow-Origin','*')]:self.send_header(key,value)
                    self.end_headers();self.wfile.write(raw)
                except (ValueError,KeyError,OSError):self.reply(404,{'error':'预览失效或资源不可用，请重新打开。'})
                return
            if not self.authorize():
                return
            path = urlsplit(self.path).path
            if path=='/api/web-product/screenshot':
                try:
                    target=self.server.web_products.screenshot_path(self.query.get('id',[''])[0])
                    with target.open('rb') as stream:
                        from artifact_preview import opened_path
                        if os.path.normcase(str(opened_path(stream,target)))!=os.path.normcase(str(target.absolute())):raise ValueError('截图位置已改变。')
                        raw=stream.read(32*1024*1024+1)
                    if len(raw)>32*1024*1024:raise ValueError('截图过大。')
                    self.reply(200,raw,'image/png')
                except (ValueError,KeyError,OSError):self.reply(404,{'error':'截图不存在，请重新生成。'})
            elif path=='/api/web-product':
                try:self.reply(200,self.server.web_products.prepare(self.query.get('id',[''])[0]))
                except (ValueError,KeyError,OSError) as error:self.reply(400,{'error':str(error)[:300]})
            elif path in ('/api/workbench', '/api/workbench-artifact'):
                self.workbench_get(path)
            elif path.startswith('/api/pc-files/'):
                self.pc_files_get(path)
            elif path == '/pc-file-search.js':
                self.reply(200,(BASE/'pc_file_search.js').read_bytes(),'application/javascript; charset=utf-8')
            elif path == '/api/workbench-sheet':
                if not self.workbench_origin():return
                try:
                    from file_review import workbench_sheet
                    self.reply(200,workbench_sheet(self.server.workbench,self.query.get('id',[''])[0],self.query.get('name',[''])[0],self.query.get('kind',['task'])[0]))
                except (ValueError,KeyError,OSError):self.reply(400,{'error':'无法读取该XLSX，请检查任务与文件状态，或下载原件。'})
            elif path == '/agent-center':
                self.ui_page('agent_center.html')
            elif path in ('/collaboration','/mobile'):
                self.ui_page('collaboration.html')
            elif path=='/' and self.query.get('desktop_embed',[''])[0]!='1':
                self.ui_page('collaboration.html')
            elif path in ('/', '/bot', '/workbench', '/sessions'):
                self.ui_page('mobile_bot.html')
            elif path == '/transfer':
                self.ui_page('index.html')
            elif path == '/desktop-embed.js':
                self.reply(200,(BASE/'desktop-embed.js').read_bytes(),'application/javascript; charset=utf-8')
            elif path == '/history.js':
                self.reply(410, {'error': '旧版页面已移除，请刷新后使用统一会话工作台。'})
            elif path == '/conversation.js':
                self.reply(200, (BASE / 'conversation.js').read_bytes(), 'application/javascript; charset=utf-8')
            elif path == '/file-viewer':
                self.reply(200, (BASE / 'file_viewer.html').read_bytes(), 'text/html; charset=utf-8')
            elif path == '/file-image':
                try:
                    data,mime=FileReview(tasks).image(self.query.get('task_id',[''])[0],self.query.get('path',[''])[0])
                    self.reply(200,data,mime)
                except (ValueError,KeyError,OSError):
                    self.reply(404,{'error':'图片不存在、不属于当前任务或格式不受支持。'})
            elif path == '/preview-viewer':
                self.reply(200,(BASE/'pdf_viewer.html').read_bytes(),'text/html; charset=utf-8')
            elif path.startswith('/preview/'):
                try:
                    import re
                    match=re.fullmatch('/preview/([a-f0-9]{64})/(document\\.pdf|page/([1-9][0-9]{0,2})\\.png)',path)
                    if not match:raise FileNotFoundError()
                    name='document.pdf' if match[2]=='document.pdf' else 'page-'+match[3]+'.png'
                    target=self.server.previews.asset(match[1],name)
                    self.send_response(200)
                    self.send_header('Content-Type','application/pdf' if name.endswith('.pdf') else 'image/png')
                    if name.endswith('.pdf'):
                        title=Path(self.server.previews.get(match[1])['title']).stem+'.preview.pdf'
                        disposition='attachment' if self.query.get('download',[''])[0]=='1' else 'inline'
                        self.send_header('Content-Disposition',disposition+"; filename*=UTF-8''"+quote(title,safe=''))
                    self.send_header('Content-Length',str(target.stat().st_size))
                    self.send_header('Cache-Control','no-store')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Referrer-Policy','no-referrer')
                    self.end_headers()
                    with target.open('rb') as stream:
                        import shutil
                        shutil.copyfileobj(stream,self.wfile)
                except (ValueError,KeyError,OSError):self.reply(404,{'error':'预览文件不存在或尚未就绪。'})
            elif path == '/api/bot/generated-image':
                try:
                    data,mime=reader.generated_image(self.query.get('thread_id',[''])[0],
                        int(self.query.get('offset',['-1'])[0]),int(self.query.get('index',['-1'])[0]))
                    self.reply(200,data,mime)
                except (ValueError,KeyError,OSError,sqlite3.Error):
                    self.reply(404,{'error':'生成的图片暂时无法读取，请刷新会话后重试。'})
            elif path.startswith('/api/bot/reply-input/'):
                try:
                    from urllib.parse import unquote
                    source=self.query.get('source_id',[''])[0]
                    bot._key('web',source)
                    job_id,name=path.removeprefix('/api/bot/reply-input/').split('/',1)
                    image=replies.attachment_path('web',source,job_id,unquote(name))
                    mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[image.suffix.lower()]
                    self.reply(200,image.read_bytes(),mime)
                except (ValueError,KeyError,OSError):
                    self.reply(404,{'error':'图片不存在或不属于当前网页。'})
            elif path.startswith('/api/bot/'):
                try:
                    source=self.query.get('source_id',[''])[0]
                    if path in ('/api/bot/files','/api/bot/file'):
                        try:
                            review=FileReview(tasks);task_id=self.query.get('task_id',[''])[0]
                            data=review.files(task_id) if path.endswith('/files') else review.read(task_id,self.query.get('path',[''])[0])
                        except OSError:
                            self.reply(404,{'error':'文件已移动或无法读取，请刷新列表后重试。'});return
                    elif path.startswith('/api/bot/preview/'):
                        data=self.server.previews.get(path.removeprefix('/api/bot/preview/'))
                    elif path=='/api/bot/usage':
                        data=self.server.usage.read()
                    elif path=='/api/bot/deepseek/balance':
                        data=self.server.deepseek_balance.read()
                    elif path=='/api/bot/diagnostics':
                        bot._key('web',source)
                        thread_id=self.query.get('thread_id',[None])[0]
                        if thread_id is not None and not 1<=len(thread_id)<=120:
                            raise ValueError('会话范围无效，请重新选择。')
                        data=server_diagnostics(self.server,source,thread_id)
                    elif path=='/api/bot/conversation':
                        before=self.query.get('before',[None])[0]
                        data=conversation_detail(tasks,reader,replies,source,
                                                 task_id=self.query.get('task_id',[None])[0],
                                                 thread_id=self.query.get('thread_id',[None])[0],
                                                 before=int(before) if before is not None else None)
                    elif path.startswith('/api/bot/desktop-open/'):
                        data=desktop_open.get(path.removeprefix('/api/bot/desktop-open/'))
                    elif path=='/api/bot/deepseek/sessions':
                        data=self.server.deepseek_history.session_page(limit=20,offset=int(self.query.get('offset',['0'])[0]),search=self.query.get('q',[''])[0])
                    elif path=='/api/bot/deepseek/conversation':
                        before=self.query.get('before',[None])[0]
                        data=self.server.deepseek_history.conversation(self.query.get('session_id',[''])[0],source,
                                                                      before=int(before) if before is not None else None,replies=self.server.deepseek_replies)
                    elif path=='/api/bot/history/sessions':
                        data=reader.session_page(limit=20,offset=int(self.query.get('offset',['0'])[0]),search=self.query.get('q',[''])[0])
                    elif path=='/api/bot/history':
                        before=self.query.get('before',[None])[0]
                        data=reader.history(self.query.get('thread_id',[''])[0],before=int(before) if before is not None else None)
                    elif path=='/api/bot/tasks':data=tasks.list()
                    elif path=='/api/bot/state':data=bot.state('web',source)
                    elif path=='/api/bot/progress':data=bot.progress('web',source)
                    elif path=='/api/bot/sessions':data={'sessions':bot.list_sessions('web',source) if source else bot.reader.sessions()}
                    elif path=='/api/bot/replies':
                        bot._key('web',source);data={'jobs':replies.list('web',source,self.query.get('thread_id',[None])[0])}
                    else:
                        self.reply(404,{'error':'Bot 接口不存在'});return
                    self.reply(200,data)
                except KeyError:
                    self.reply(404,{'error':'会话或任务不存在，请重新选择。'})
                except (OSError,ValueError,sqlite3.Error) as e:
                    self.reply(400,{'error':str(e)})
            elif path == '/api/agents':
                self.reply(200, agents())
            elif path == '/api/tasks':
                self.reply(200, tasks.list())
            elif path.startswith('/api/tasks/'):
                try:
                    self.reply(200, tasks.get(path.removeprefix('/api/tasks/')))
                except KeyError:
                    self.reply(404, {'error': '任务不存在'})
            elif path.startswith('/input/'):
                try:
                    from urllib.parse import unquote
                    task_id, name = path.removeprefix('/input/').split('/', 1)
                    name = unquote(name)
                    task = tasks.get(task_id)
                    workspace = tasks.workspace(task_id).resolve()
                    inputs = workspace / 'inputs'
                    base = inputs.resolve()
                    if (not workspace.is_relative_to(tasks.data.resolve()) or inputs.is_symlink()
                            or inputs.is_junction() or not base.is_relative_to(workspace)):
                        raise FileNotFoundError()
                    target = base / name
                    if (name not in task['attachments'] or Path(name).name != name or '/' in name or '\\' in name
                            or target.is_symlink() or not target.resolve().is_relative_to(base) or not target.is_file()):
                        raise FileNotFoundError()
                    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(target.suffix.lower())
                    if mime:
                        self.reply(200, target.read_bytes(), mime)
                    else:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(name))
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', str(target.stat().st_size))
                        self.end_headers()
                        with target.open('rb') as source:
                            import shutil
                            shutil.copyfileobj(source, self.wfile)
                except (ValueError, KeyError, FileNotFoundError):
                    self.reply(404, {'error': '任务附件不存在'})
            elif path.startswith('/artifact/'):
                try:
                    task_id, name = path.removeprefix('/artifact/').split('/', 1)
                    from urllib.parse import unquote
                    artifact = tasks.artifact_path(task_id, unquote(name))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(artifact.name))
                    self.send_header('Content-Length', str(artifact.stat().st_size))
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    with artifact.open('rb') as source:
                        import shutil
                        shutil.copyfileobj(source, self.wfile)
                except (ValueError, KeyError, FileNotFoundError):
                    self.reply(404, {'error': '成果文件不存在'})
            elif path == '/api/info':
                network=self.server.refresh_network()
                self.reply(200, {'urls': network['urls'], 'remote_access': network['remote_access'], 'folder': str(folder), 'limit': MAX_BYTES, 'reply_mode': 'native-writer-v1', 'ui_mode': 'unified-only', 'backend_revision':'2026-11-12-partner-mobile', 'capabilities':{'partner_group_chat':True,'deepseek_resume':True,'workbench_preview':True,'code_collaboration':True,'public_website_reference':True,'web_product_preview':True}})
            elif path == '/api/files':
                items = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
                self.reply(200, [{'name': p.name, 'size': p.stat().st_size, 'time': p.stat().st_mtime} for p in items])
            elif path == '/api/messages':
                self.reply(200, messages.list())
            elif path == '/qr.svg':
                import qrcode
                import qrcode.image.svg
                urls=self.server.refresh_network()['urls']
                address=self.query.get('address',[None])[0]
                if address is not None:
                    if address not in urls:
                        self.reply(410, {'error': '此连接地址已变化，请刷新连接信息后重新扫码。'})
                        return
                else:
                    try:index=int(self.query.get('index',['0'])[0])
                    except ValueError:index=-1
                    if not 0 <= index < len(urls):
                        self.reply(400, {'error': '没有可用的连接地址'})
                        return
                    address=urls[index]
                qr = qrcode.make(address, image_factory=qrcode.image.svg.SvgPathImage)
                buffer = io.BytesIO()
                qr.save(buffer)
                self.reply(200, buffer.getvalue(), 'image/svg+xml')
            elif path.startswith('/file/'):
                from urllib.parse import unquote
                name = unquote(path[6:])
                if Path(name).name != name or '/' in name or '\\' in name or Path(name).suffix.lower() not in EXTENSIONS:
                    self.reply(400, {'error': '无效的文件名'})
                    return
                target = folder / name
                if not target.is_file():
                    self.reply(404, {'error': '文件不存在'})
                    return
                self.reply(200, target.read_bytes(), mimetypes.guess_type(name)[0] or 'application/octet-stream')
            else:
                self.reply(404, {'error': '页面不存在'})

        def do_POST(self):
            try:
                self._remaining_body = max(0, int(self.headers.get('Content-Length', '0')))
            except ValueError:
                self._remaining_body = 0
            if not self.authorize():
                return
            if urlsplit(self.path).path == '/api/workbench':
                self.workbench_post()
                return
            if urlsplit(self.path).path=='/api/web-product/screenshot':
                if not self.workbench_origin():return
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict) or set(payload)!={'id'}:raise ValueError('仅接受项目任务编号。')
                    base='http://127.0.0.1:'+str(self.server.server_port)
                    self.reply(200,self.server.web_products.screenshot(payload['id'],base))
                except (ValueError,KeyError,OSError) as error:self.reply(400,{'error':str(error)[:300]})
                return
            if urlsplit(self.path).path == '/api/workbench-preview':
                if not self.workbench_origin():return
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict) or set(payload)-{'id','name','kind'} or not {'id','name'}<=set(payload):raise ValueError('预览参数无效。')
                    result=self.server.workbench.call(artifact_action(payload.get('kind','task')),{k:payload[k] for k in ('id','name')})
                    if not result.get('ok'):
                        self.reply(400,{'error':result.get('error') or '成果暂不可用，请刷新后重试。'});return
                    data=result['data']
                    if data.get('name')!=payload['name']:raise ValueError('返回文件与所选成果不一致。')
                    raw=base64.b64decode(data['content_base64'],validate=True)
                    receipt=self.server.previews.create_bytes(payload['id'],payload['name'],raw,**({'kind':'collaboration'} if payload.get('kind')=='collaboration' else {}))
                    self.reply(200 if receipt['status']=='ready' else 202,receipt)
                except (ValueError,KeyError,OSError):self.reply(400,{'error':'预览暂不可用，请尝试下载原文件；未修改任务或原成果。'})
                return
            if urlsplit(self.path).path == '/api/bot/preview':
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict) or set(payload)!={'task_id','path'}:raise ValueError('预览请求格式无效。')
                    data=self.server.previews.create(payload['task_id'],payload['path'])
                    self.reply(200 if data['status']=='ready' else 202,data)
                except (KeyError,FileNotFoundError):self.reply(404,{'error':'成果文件不存在，请刷新任务。'})
                except (ValueError,UnicodeError,OSError):self.reply(400,{'error':'无法创建预览，请确认成果格式、文件状态或稍后重试。'})
                return
            if urlsplit(self.path).path == '/api/bot/deepseek/reply':
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict) or set(payload)-{'source_id','session_id','text','request_id'}:raise ValueError('续聊参数无效')
                    job=self.server.deepseek_replies.create('web',payload.get('source_id'),payload.get('request_id'),payload.get('session_id'),payload.get('text'))
                    self.reply(200,{'job':job,'text':'续聊已保存，电脑会检查原会话占用后执行。'})
                except (ValueError,KeyError,OSError):self.reply(400,{'error':'此会话暂不能继续或已有指令，请刷新查看原因。原文请保留，不要重复提交。'})
                return
            if urlsplit(self.path).path.startswith('/api/bot/deepseek/replies/') and urlsplit(self.path).path.endswith('/cancel'):
                try:
                    payload=self.read_json();identifier=urlsplit(self.path).path.split('/')[-2]
                    if not isinstance(payload,dict) or set(payload)-{'source_id'}:raise ValueError('参数无效')
                    self.reply(200,{'job':self.server.deepseek_replies.cancel('web',payload.get('source_id'),identifier)})
                except (ValueError,KeyError,OSError):self.reply(400,{'error':'该指令不可取消，请刷新核对。'})
                return
            if urlsplit(self.path).path == '/api/bot/history/reply':
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict):raise ValueError('指令格式不正确')
                    self.reply(200,bot.reply_to('web',payload.get('source_id'),payload.get('thread_id'),payload.get('text',''),payload.get('request_id'),attachments=payload.get('attachments')))
                except KeyError:
                    self.reply(404,{'error':'目标会话不存在或已归档，未发送。'})
                except (ValueError,UnicodeError,OSError,sqlite3.Error) as e:
                    self.reply(400,{'error':str(e)})
                return
            if urlsplit(self.path).path == '/api/bot/desktop-open':
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict) or set(payload)-{'task_id','thread_id'}:
                        raise ValueError('打开请求格式不正确，请重新选择当前会话。')
                    task_id=payload.get('task_id')
                    if task_id is not None and (not isinstance(task_id,str) or not 1<=len(task_id)<=128):
                        raise ValueError('无效的任务标识。')
                    self.reply(200,desktop_open.request(task_id=task_id,thread_id=payload.get('thread_id')))
                except KeyError:
                    self.reply(404,{'error':'目标会话或任务不存在，请重新选择。'})
                except (ValueError,UnicodeError,OSError,sqlite3.Error) as e:
                    self.reply(400,{'error':str(e)})
                return
            if urlsplit(self.path).path.startswith('/api/bot/tasks/') and urlsplit(self.path).path.endswith('/open-codex'):
                self.reply(410, {'error': '桌面打开入口已移除，请通过统一工作台操作。'})
                return
            if urlsplit(self.path).path == '/api/bot/tasks':
                try:
                    task = create_bot_task(tasks, self.read_json())
                    self.reply(201, task)
                except (ValueError, UnicodeError) as e:
                    self.reply(400, {'error': str(e)})
                return
            if urlsplit(self.path).path == '/api/bot/reply':
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict):raise ValueError('回复格式不正确')
                    data=bot.reply('web',payload.get('source_id'),payload.get('text',''),payload.get('request_id'),payload.get('expected_thread_id'),attachments=payload.get('attachments'))
                    self.reply(200,data)
                except (ValueError,KeyError,OSError,sqlite3.Error) as e:self.reply(400,{'error':str(e)})
                return
            if urlsplit(self.path).path.startswith('/api/bot/replies/') and urlsplit(self.path).path.endswith('/cancel'):
                try:
                    payload=self.read_json();source=payload.get('source_id');bot._key('web',source)
                    job_id=urlsplit(self.path).path.split('/')[-2]
                    self.reply(200,{'job':replies.cancel('web',source,job_id)})
                except (ValueError,KeyError) as e:self.reply(409,{'error':str(e)})
                return
            if urlsplit(self.path).path == '/api/bot/message':
                try:
                    payload=self.read_json()
                    if not isinstance(payload,dict):raise ValueError('Bot 请求格式不正确')
                    self.reply(200,bot.handle('web',payload.get('source_id'),payload.get('text'),payload.get('request_id')))
                except (ValueError,UnicodeError,sqlite3.Error) as e:
                    self.reply(400,{'error':str(e)})
                return
            if urlsplit(self.path).path == '/api/messages':
                self.receive_message()
                return
            if urlsplit(self.path).path == '/api/tasks':
                try:
                    payload = self.read_json()
                    task = tasks.create(payload)
                    self.reply(201, task)
                except (ValueError, UnicodeError) as e:
                    self.reply(400, {'error': str(e)})
                return
            if urlsplit(self.path).path.startswith('/api/tasks/') and urlsplit(self.path).path.endswith('/cancel'):
                try:
                    task_id = urlsplit(self.path).path.split('/')[-2]
                    self.reply(200, tasks.cancel(task_id))
                except KeyError:
                    self.reply(404, {'error': '任务不存在'})
                return
            if urlsplit(self.path).path == '/api/task-upload':
                self.receive_attachment()
                return
            if urlsplit(self.path).path != '/api/upload':
                self.reply(404, {'error': '接口不存在'})
                return
            name = self.query.get('name', [''])[0]
            if (not name or len(name) > 180 or name != Path(name).name or
                    any(c in name for c in '/\\<>:"|?*') or any(ord(c) < 32 for c in name) or
                    Path(name).suffix.lower() not in EXTENSIONS):
                self.reply(400, {'error': '请选择图片文件，文件名不能包含路径或特殊字符。'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BYTES:
                self.reply(400, {'error': '图片不能为空，且单张不能超过 100 MB。'})
                return
            temp = folder / ('.upload-' + secrets.token_hex(12))
            try:
                self.connection.settimeout(60)
                remaining = length
                with temp.open('xb') as f:
                    while remaining:
                        block = self.read_body(min(remaining, 256 * 1024))
                        if not block:
                            raise OSError('上传中断')
                        f.write(block)
                        remaining -= len(block)
                with write_lock:
                    # Unique prefix prevents overwrites and Windows reserved names.
                    saved = time.strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(4) + '-' + name
                    temp.rename(folder / saved)
                self.reply(201, {'name': saved, 'size': length})
            except (OSError, TimeoutError):
                try:
                    self.reply(500, {'error': '保存失败，请检查磁盘空间或重试。'})
                except OSError:
                    pass
            finally:
                temp.unlink(missing_ok=True)

        def receive_message(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 128 * 1024:
                    raise ValueError('消息太长或内容为空。')
                self.connection.settimeout(15)
                payload = json.loads(self.read_body(length))
                if not isinstance(payload, dict):
                    raise ValueError('消息格式不正确。')
                item = messages.add(payload.get('text'), payload.get('sender', 'phone'), payload.get('client_id'))
            except (ValueError, UnicodeError) as e:
                self.reply(400, {'error': str(e) if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else '消息格式不正确。'})
                return
            except (OSError, sqlite3.Error):
                self.reply(500, {'error': '消息未保存，请稍后重试。'})
                return
            self.reply(201, item)

        def read_json(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 256*1024:
                raise ValueError('提交内容为空或太长')
            self.connection.settimeout(20)
            return json.loads(self.read_body(length))

        def read_body(self, length):
            data = self.rfile.read(length)
            self._remaining_body = max(0, getattr(self, '_remaining_body', 0) - len(data))
            return data

        def receive_attachment(self):
            name = self.query.get('name', [''])[0]
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if (not name or len(name)>180 or any(c in name for c in '/\\<>:"|?*') or any(ord(c)<32 for c in name)
                        or not 0 < length <= MAX_BYTES):
                    raise ValueError('附件名无效，或文件为空、超过 100 MB')
            except ValueError as e:
                self.reply(400, {'error': str(e)})
                return
            saved = secrets.token_hex(6) + '-' + name
            path = tasks.uploads / saved
            temp = tasks.uploads / ('.upload-' + secrets.token_hex(12))
            try:
                self.connection.settimeout(90)
                remaining = length
                with temp.open('xb') as f:
                    while remaining:
                        block = self.read_body(min(remaining, 256*1024))
                        if not block:
                            raise OSError('上传中断')
                        f.write(block)
                        remaining -= len(block)
                temp.rename(path)
                self.reply(201, {'name': saved, 'original': name, 'size': length})
            except OSError:
                self.reply(500, {'error': '附件保存失败，请重试'})
            finally:
                temp.unlink(missing_ok=True)

    server = ThreadingHTTPServer((host, port), Handler)
    server.started_at = time.monotonic()
    try:
        reader=CodexSessionReader()
        # Claim ownership before recovery can modify persisted task states.
        # No execution starts until every component is initialized.
        replies=ReplyQueue(folder.parent,reader,start_worker=False)
        deepseek_history=DeepSeekHistoryReader()
        deepseek_replies=DeepSeekReplies(folder.parent,deepseek_history,start_worker=False)
        messages = MessageStore(folder.parent / '消息记录.sqlite3')
        tasks = TaskManager(folder.parent,start_worker=False)
        bot = BotCore(folder.parent / 'Bot记录.sqlite3', reader,replies)
        desktop_open = DesktopOpenManager(tasks,reader,replies)
        previews=PreviewService(tasks)
    except Exception:
        if 'replies' in locals():replies.close()
        if 'deepseek_replies' in locals():deepseek_replies.close()
        if 'tasks' in locals():tasks.close()
        server.server_close()
        raise
    server.daemon_threads = True
    server.urls = [f'http://{ip}:{server.server_port}/?token={token}' for ip in local_ips()]
    server.network_access = NetworkAccess(server.urls,server.server_port,token)
    def refresh_network():
        network=server.network_access.snapshot()
        server.urls=network['urls']
        return network
    server.refresh_network=refresh_network
    server.folder = folder
    server.token = token
    server.messages = messages
    server.tasks = tasks
    server.workbench = WorkbenchProxy(BASE, tasks.uploads)
    from pc_files import ComputerFiles
    server.pc_files=ComputerFiles(folder.parent)
    server.bot = bot
    server.usage = UsageService()
    server.deepseek_balance = DeepSeekBalanceService()
    server.deepseek_history = deepseek_history
    server.deepseek_replies = deepseek_replies
    server.desktop_open = desktop_open
    server.previews = previews
    from web_product import WebProducts
    server.web_products=WebProducts(tasks)
    original_close = server.server_close
    def close_server():
        previews.close()
        server.usage.close()
        server.deepseek_balance.close()
        desktop_open.close()
        replies.close()
        deepseek_replies.close()
        tasks.close()
        original_close()
    server.server_close = close_server
    tasks.start()
    replies.start()
    deepseek_replies.start()
    return server


def desktop(server):
    import tkinter as tk
    from tkinter import ttk
    import webbrowser
    import qrcode

    BG = '#f3f6fa'
    PANEL = '#ffffff'
    LINE = '#dde5ee'
    INK = '#1f2a3a'
    MUTED = '#5f6f83'
    FAINT = '#8493a5'
    ACCENT = '#2f6fe4'
    ACCENT_DARK = '#1f5bd0'
    ACCENT_SOFT = '#e8f0fe'
    FONT = 'Microsoft YaHei UI'

    def tailnet_url(url):
        try:
            parts = (urlsplit(url).hostname or '').split('.')
            return len(parts) == 4 and int(parts[0]) == 100 and 64 <= int(parts[1]) <= 127
        except ValueError:
            return False

    def network_labels(urls):
        kinds = ['Tailscale 远程' if tailnet_url(url) else '同一 Wi-Fi' for url in urls]
        totals = {kind: kinds.count(kind) for kind in set(kinds)}
        seen = {}
        labels = []
        for kind in kinds:
            seen[kind] = seen.get(kind, 0) + 1
            labels.append(kind if totals[kind] == 1 else f'{kind} {seen[kind]}')
        return labels

    def size_text(value):
        number = max(0, int(value or 0))
        if number >= 1024 * 1024:
            return f'{number / (1024 * 1024):.1f} MB'
        if number >= 1024:
            return f'{number / 1024:.0f} KB'
        return f'{number} B'

    def scrollable(parent):
        outer = tk.Frame(parent, bg=BG)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        content = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=content, anchor='nw')

        def fit_width(event):
            canvas.itemconfigure(window, width=event.width)

        def fit_scroll(_=None):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def on_wheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
            return 'break'

        canvas.bind('<Configure>', fit_width)
        content.bind('<Configure>', fit_scroll)
        canvas.bind('<MouseWheel>', on_wheel)
        content.bind('<MouseWheel>', on_wheel)
        parent.after_idle(fit_scroll)
        return outer, content

    root = tk.Tk()
    root.title('远程会话台')
    root.geometry('820x720')
    root.minsize(680, 640)
    root.configure(bg=BG)
    root.option_add('*Font', (FONT, 10))

    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure('TNotebook.Tab', padding=(18, 9), font=(FONT, 10), background='#e9eff7', foreground=MUTED, borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', PANEL)], foreground=[('selected', INK)])
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=INK, rowheight=32, borderwidth=0, font=(FONT, 10))
    style.configure('Treeview.Heading', background='#f1f5fa', foreground=MUTED, font=(FONT, 9, 'bold'), relief='flat', padding=(8, 7))
    style.map('Treeview', background=[('selected', ACCENT_SOFT)], foreground=[('selected', INK)])
    style.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=INK, padding=6)
    style.map('TCombobox', fieldbackground=[('readonly', PANEL)], selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', INK)])
    style.configure('Vertical.TScrollbar', background='#cfd9e6', troughcolor=BG, borderwidth=0, arrowcolor=MUTED)

    header = tk.Frame(root, bg=BG)
    header.pack(fill='x', padx=24, pady=(20, 12))
    title_row = tk.Frame(header, bg=BG)
    title_row.pack(fill='x')
    tk.Label(title_row, text='远程会话台', bg=BG, fg=INK, font=(FONT, 22, 'bold')).pack(side='left')
    tk.Label(title_row, text='接收中', bg=ACCENT_SOFT, fg=ACCENT_DARK, font=(FONT, 9, 'bold'), padx=10, pady=4).pack(side='right')
    tk.Label(header, text='手机接收记录与传输', bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(5, 0))

    buttons = tk.Frame(root, bg=BG)
    buttons.pack(fill='x', padx=24)

    def action_button(text, command, primary=False):
        return tk.Button(
            buttons, text=text, command=command,
            font=(FONT, 10, 'bold' if primary else 'normal'),
            bg=ACCENT if primary else PANEL,
            fg='#ffffff' if primary else INK,
            activebackground=ACCENT_DARK if primary else '#eef3fa',
            activeforeground='#ffffff' if primary else INK,
            relief='flat', borderwidth=0, padx=16, pady=9, cursor='hand2',
            highlightthickness=1, highlightbackground=ACCENT if primary else LINE,
        )

    action_button('打开工作台', lambda: webbrowser.open(f'http://127.0.0.1:{server.server_port}/?token={server.token}'), primary=True).pack(side='left', padx=(0, 8))
    action_button('图片 / 文字传输', lambda: webbrowser.open(f'http://127.0.0.1:{server.server_port}/transfer?token={server.token}')).pack(side='left', padx=(0, 8))
    action_button('接收文件夹', lambda: os.startfile(server.folder)).pack(side='left')

    status_bar = tk.Frame(root, bg=ACCENT_SOFT)
    status_bar.pack(fill='x', padx=24, pady=(12, 0))
    tk.Label(status_bar, text='●', bg=ACCENT_SOFT, fg=ACCENT, font=(FONT, 10)).pack(side='left', padx=(12, 7), pady=7)
    tk.Label(status_bar, text='接收服务运行中 · 关闭窗口会停止接收', bg=ACCENT_SOFT, fg=ACCENT_DARK, font=(FONT, 9)).pack(side='left', pady=7)
    tk.Label(status_bar, text='重启后恢复，无需重新扫码', bg=ACCENT_SOFT, fg=MUTED, font=(FONT, 9)).pack(side='right', padx=12, pady=7)

    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True, padx=24, pady=(10, 8))
    records_page = tk.Frame(notebook, bg=BG)
    message_page = tk.Frame(notebook, bg=BG)
    pairing_page = tk.Frame(notebook, bg=BG)
    notebook.add(records_page, text='  接收记录  ')
    notebook.add(message_page, text='  文字消息  ')
    notebook.add(pairing_page, text='  手机配对  ')
    notebook.select(records_page)

    records_head = tk.Frame(records_page, bg=BG)
    records_head.pack(fill='x', padx=4, pady=(12, 4))
    tk.Label(records_head, text='最近收到', bg=BG, fg=INK, font=(FONT, 13, 'bold')).pack(side='left')
    records_count = tk.StringVar(value='0 张 · 还没有收到图片')
    tk.Label(records_head, textvariable=records_count, bg=BG, fg=MUTED, font=(FONT, 9)).pack(side='right')
    tk.Label(records_page, text='双击打开 · 原文件保存在接收文件夹', bg=BG, fg=FAINT, font=(FONT, 9)).pack(anchor='w', padx=4, pady=(0, 8))
    records_body = tk.Frame(records_page, bg=BG)
    records_body.pack(fill='both', expand=True, padx=4, pady=(0, 12))
    listing = ttk.Treeview(records_body, columns=('name', 'size', 'time'), show='headings', height=10)
    listing.heading('name', text='文件')
    listing.heading('size', text='大小')
    listing.heading('time', text='收到时间')
    listing.column('name', width=330, minwidth=180, anchor='w', stretch=True)
    listing.column('size', width=80, minwidth=60, anchor='e', stretch=False)
    listing.column('time', width=130, minwidth=110, anchor='e', stretch=False)
    records_scroll = ttk.Scrollbar(records_body, orient='vertical', command=listing.yview)
    listing.configure(yscrollcommand=records_scroll.set)
    listing.pack(side='left', fill='both', expand=True)
    records_scroll.pack(side='right', fill='y')
    displayed = []
    message_items = []

    def open_selected(_=None):
        selection = listing.selection()
        if not selection:
            return
        try:
            os.startfile(displayed[int(selection[0])])
        except (IndexError, OSError):
            records_count.set('文件暂时无法打开')

    listing.bind('<Double-Button-1>', open_selected)

    message_scroll_frame, message_content = scrollable(message_page)
    message_scroll_frame.pack(fill='both', expand=True, padx=4, pady=(0, 4))

    message_head = tk.Frame(message_content, bg=BG)
    message_head.pack(fill='x', padx=4, pady=(10, 4))
    tk.Label(message_head, text='电脑 → 手机', bg=BG, fg=INK, font=(FONT, 13, 'bold')).pack(side='left')
    tk.Label(message_head, text='传输消息', bg=ACCENT_SOFT, fg=ACCENT_DARK, font=(FONT, 9, 'bold'), padx=9, pady=3).pack(side='right')
    tk.Label(message_content, text='传输消息，不发布为 Agent 任务；发布任务请使用工作台。', bg=BG, fg=MUTED, font=(FONT, 9), wraplength=580, justify='left').pack(anchor='w', padx=4, pady=(0, 6))

    list_frame = tk.Frame(message_content, bg=BG)
    list_frame.pack(fill='x', padx=4)
    message_list = tk.Listbox(
        list_frame, height=3, exportselection=False, activestyle='none', relief='flat', borderwidth=0,
        bg=PANEL, fg=INK, selectbackground=ACCENT_SOFT, selectforeground=INK,
        highlightthickness=1, highlightbackground=LINE, font=(FONT, 10),
    )
    message_list_scroll = ttk.Scrollbar(list_frame, orient='vertical', command=message_list.yview)
    message_list.configure(yscrollcommand=message_list_scroll.set)
    message_list.pack(side='left', fill='x', expand=True)
    message_list_scroll.pack(side='right', fill='y')
    message_detail = tk.Text(
        message_content, height=4, wrap='word', relief='flat', borderwidth=0, padx=12, pady=8,
        bg='#f8fafc', fg=INK, highlightthickness=1, highlightbackground=LINE,
        font=(FONT, 10), state='disabled',
    )
    message_detail.pack(fill='x', padx=4, pady=(6, 0))
    message_status = tk.StringVar(value='可发送文字、链接或多行笔记，每条最多 10000 字；只传输到手机。')

    def show_message(_=None):
        selected = message_list.curselection()
        message_detail.config(state='normal')
        message_detail.delete('1.0', 'end')
        if selected and selected[0] < len(message_items):
            message_detail.insert('1.0', message_items[selected[0]]['text'])
        message_detail.config(state='disabled')

    def copy_message():
        selected = message_list.curselection()
        if not selected:
            message_status.set('请先选择一条消息。')
            return
        root.clipboard_clear()
        root.clipboard_append(message_items[selected[0]]['text'])
        message_status.set('已复制，可以粘贴到其他软件。')

    message_list.bind('<<ListboxSelect>>', show_message)
    message_actions = tk.Frame(message_content, bg=BG)
    message_actions.pack(fill='x', padx=4, pady=4)
    tk.Button(
        message_actions, text='复制这条文字', command=copy_message, font=(FONT, 9),
        bg=PANEL, fg=INK, activebackground='#eef3fa', activeforeground=INK,
        relief='flat', borderwidth=0, padx=12, pady=7, cursor='hand2',
        highlightthickness=1, highlightbackground=LINE,
    ).pack(side='right')

    tk.Label(message_content, text='发送到手机（传输消息）', bg=BG, fg=INK, font=(FONT, 9, 'bold')).pack(anchor='w', padx=4)
    composer = tk.Text(
        message_content, height=3, wrap='word', relief='flat', borderwidth=0, padx=10, pady=8,
        bg=PANEL, fg=INK, highlightthickness=1, highlightbackground=LINE, font=(FONT, 10),
    )
    composer.pack(fill='x', padx=4, pady=(4, 4))

    def send_message(_=None):
        text = composer.get('1.0', 'end-1c')
        try:
            server.messages.add(text, 'computer', secrets.token_hex(16))
        except (ValueError, sqlite3.Error) as e:
            message_status.set(str(e) if isinstance(e, ValueError) else '保存失败，请检查磁盘空间。')
            return 'break'
        composer.delete('1.0', 'end')
        message_status.set('已发送到手机。发布 Agent 任务请使用工作台。')
        refresh_messages()
        message_list.selection_clear(0, 'end')
        message_list.selection_set('end')
        message_list.see('end')
        show_message()
        return 'break'

    send_row = tk.Frame(message_content, bg=BG)
    send_row.pack(fill='x', padx=4, pady=(0, 0))
    tk.Button(
        send_row, text='发送消息', command=send_message, font=(FONT, 10, 'bold'),
        bg=ACCENT, fg='#ffffff', activebackground=ACCENT_DARK, activeforeground='#ffffff',
        relief='flat', borderwidth=0, padx=20, pady=8, cursor='hand2',
        highlightthickness=1, highlightbackground=ACCENT,
    ).pack(side='right')
    tk.Label(message_content, textvariable=message_status, bg=BG, fg=MUTED, font=(FONT, 9), wraplength=580, anchor='w', justify='left').pack(fill='x', padx=4, pady=(4, 8))
    composer.bind('<Control-Return>', send_message)

    def refresh_messages():
        nonlocal message_items
        items = server.messages.list()
        if items == message_items:
            return
        selected = message_list.curselection()
        previous_id = message_items[selected[0]]['id'] if selected and selected[0] < len(message_items) else None
        follow = not selected or selected[0] == len(message_items) - 1
        message_items = items
        message_list.delete(0, 'end')
        for item in items:
            who = '手机' if item['sender'] == 'phone' else '电脑'
            preview = ' '.join(item['text'].split())[:80]
            message_list.insert('end', f"{who} · {time.strftime('%H:%M', time.localtime(item['time']))}   {preview}")
        if items:
            index = len(items) - 1 if follow else next((i for i, item in enumerate(items) if item['id'] == previous_id), len(items) - 1)
            message_list.selection_set(index)
            message_list.see(index)
        show_message()
        phone_count = sum(item['sender'] == 'phone' for item in items)
        notebook.tab(message_page, text=f'  文字消息 ({phone_count})  ' if phone_count else '  文字消息  ')

    pair_scroll_frame, pair_content = scrollable(pairing_page)
    pair_scroll_frame.pack(fill='both', expand=True, padx=4, pady=(0, 4))

    pair_head = tk.Frame(pair_content, bg=BG)
    pair_head.pack(fill='x', padx=4, pady=(10, 4))
    tk.Label(pair_head, text='手机连接', bg=BG, fg=INK, font=(FONT, 13, 'bold')).pack(side='left')
    tk.Label(pair_head, text='同一 Wi-Fi 或 Tailscale', bg=ACCENT_SOFT, fg=ACCENT_DARK, font=(FONT, 9, 'bold'), padx=9, pady=3).pack(side='right')
    tk.Label(pair_content, text='用 iPhone 相机扫码，然后在 Safari 打开。首次配对后可添加到手机主屏幕，之后从主屏幕进入。', bg=BG, fg=MUTED, font=(FONT, 9), wraplength=580, justify='left').pack(anchor='w', padx=4, pady=(0, 4))

    addresses = list(server.refresh_network()['urls'] or [f'http://127.0.0.1:{server.server_port}/?token={server.token}'])
    labels = network_labels(addresses)
    choice = tk.StringVar(value=labels[0] if labels else '')
    url_var = tk.StringVar(value=addresses[0] if addresses else '')
    pair_status = tk.StringVar(value='')
    canvas = tk.Canvas(pair_content, width=200, height=200, bg='white', highlightthickness=1, highlightbackground=LINE)
    canvas.pack(pady=6)

    def draw_qr(url):
        canvas.delete('all')
        if not url:
            return
        matrix = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
        matrix.add_data(url)
        matrix.make(fit=True)
        cells = matrix.get_matrix()
        scale = 200 / len(cells)
        for y, row in enumerate(cells):
            for x, black in enumerate(row):
                if black:
                    canvas.create_rectangle(x * scale, y * scale, (x + 1) * scale, (y + 1) * scale, fill='#1f2a3a', outline='')

    def selected_url():
        if not addresses:
            return ''
        try:
            return addresses[labels.index(choice.get())]
        except ValueError:
            return addresses[0]

    def show_network(_=None):
        url = selected_url()
        url_var.set(url)
        draw_qr(url)
        if not url:
            pair_status.set('没有可用的连接地址，请检查电脑网络。')

    network_row = tk.Frame(pair_content, bg=BG)
    network_row.pack(fill='x', padx=4, pady=(2, 0))
    tk.Label(network_row, text='连接方式', bg=BG, fg=FAINT, font=(FONT, 9)).pack(anchor='w')
    network_combo = ttk.Combobox(network_row, textvariable=choice, values=labels, state='readonly', font=(FONT, 10))
    network_combo.pack(fill='x', pady=(4, 0))
    network_combo.bind('<<ComboboxSelected>>', show_network)

    url_row = tk.Frame(pair_content, bg=BG)
    url_row.pack(fill='x', padx=4, pady=(8, 0))
    url_box = tk.Entry(
        url_row, textvariable=url_var, state='readonly', readonlybackground=PANEL, fg=INK,
        relief='flat', borderwidth=0, highlightthickness=1, highlightbackground=LINE, font=(FONT, 9),
    )
    url_box.pack(side='left', fill='x', expand=True, ipady=5)

    def copy_url():
        url = url_var.get()
        if not url:
            return
        root.clipboard_clear()
        root.clipboard_append(url)
        pair_status.set('链接已复制，可发送给已配对的手机。')

    tk.Button(
        url_row, text='复制链接', command=copy_url, font=(FONT, 9),
        bg=PANEL, fg=ACCENT_DARK, activebackground='#eef3fa', activeforeground=ACCENT_DARK,
        relief='flat', borderwidth=0, padx=12, pady=7, cursor='hand2',
        highlightthickness=1, highlightbackground=LINE,
    ).pack(side='right', padx=(8, 0))

    tk.Label(pair_content, textvariable=pair_status, bg=BG, fg=MUTED, font=(FONT, 9), wraplength=580, anchor='w', justify='left').pack(fill='x', padx=4, pady=(6, 0))
    network_status = tk.StringVar(value='')
    tk.Label(pair_content, textvariable=network_status, bg=BG, fg=FAINT, font=(FONT, 9), wraplength=580, anchor='w', justify='left').pack(fill='x', padx=4, pady=(4, 0))
    tk.Label(pair_content, text='首次扫码后可在手机主屏幕打开，重启接收器通常无需重新扫码。\n连接不上时，请检查 Windows 防火墙是否允许 Python 在专用网络通信。', bg=BG, fg=FAINT, font=(FONT, 9), wraplength=580, anchor='w', justify='left').pack(fill='x', padx=4, pady=(8, 10))

    def refresh():
        nonlocal addresses, labels, displayed
        network = server.refresh_network()
        updated = list(network['urls'] or [f'http://127.0.0.1:{server.server_port}/?token={server.token}'])
        if updated != addresses:
            previous = selected_url() if addresses else ''
            addresses = updated
            labels = network_labels(addresses)
            network_combo.configure(values=labels)
            if previous in addresses:
                choice.set(labels[addresses.index(previous)])
            elif labels:
                choice.set(labels[0])
            show_network()
        elif labels and choice.get() not in labels:
            choice.set(labels[0])
            show_network()
        network_status.set(network.get('remote_access', {}).get('message', ''))
        items = sorted((p for p in server.folder.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        if items != displayed:
            displayed = items
            listing.delete(*listing.get_children())
            for index, path in enumerate(items):
                stat = path.stat()
                listing.insert('', 'end', iid=str(index), values=(path.name, size_text(stat.st_size), time.strftime('%m-%d %H:%M', time.localtime(stat.st_mtime))))
            records_count.set(f'{len(items)} 张' if items else '0 张 · 还没有收到图片')
        refresh_messages()
        root.after(1500, refresh)

    def close_window():
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', close_window)
    tk.Label(root, text='原文件保存在接收文件夹', bg=BG, fg=FAINT, font=(FONT, 9)).pack(pady=(0, 10))
    show_network()
    refresh()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--reset-pairing', action='store_true', help='重置配对，使所有旧链接失效；请先关闭接收器')
    args = parser.parse_args()
    folder = BASE.parent / '收到的图片'
    try:
        token = secrets.token_urlsafe(24) if args.reset_pairing else load_token(BASE / 'pairing.json')
        server = create_server('0.0.0.0', args.port, folder, token)
        if args.reset_pairing:
            save_token(BASE / 'pairing.json', token)
    except (OSError, ValueError) as e:
        import tkinter.messagebox
        tkinter.messagebox.showerror('随手传图启动失败', f'端口 {args.port} 可能已被占用。请检查是否已经启动了随手传图。\n{e}')
        return
    state = {'port': server.server_port, 'pid': os.getpid(), 'urls': server.refresh_network()['urls'], 'local': f'http://127.0.0.1:{server.server_port}/?token={server.token}', 'folder': str(folder)}
    (BASE / 'runtime.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if args.headless:
            thread.join()
        else:
            desktop(server)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()

