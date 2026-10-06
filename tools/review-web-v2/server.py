from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from urllib.parse import urlsplit,unquote
import os,json,re,secrets,hmac,subprocess,threading,hashlib,sys,time
from http.cookies import SimpleCookie
from store import Store,Conflict,Invalid
from workflow import Workflow
ROOT=Path(__file__).resolve().parent;RUN=ROOT.parent;PUBLIC=ROOT/'public'
PORT=int(os.environ.get('REVIEW_PORT','8080'));ORIGIN=f'http://127.0.0.1:{PORT}'
STORE=Store(Path(os.environ.get('REVIEW_MANIFEST',str(RUN/'review-web/public/data/index.json'))),RUN/'review-web/public/data',ROOT/'history')
WORKFLOW=Workflow(STORE)
AUTH=json.loads((ROOT/'access.json').read_text())
SESSIONS={};LOGIN_ATTEMPTS={}
TOKEN=secrets.token_urlsafe(32);RENDER_LOCK=threading.RLock()

def rendered(id,language):
 d=STORE.docs[id];digest=STORE.catalog(d['output'])[2] if language=='ko' else 'source-v1'
 path=ROOT/'rendered'/(id+'-'+language+'-'+digest+'.html')
 with RENDER_LOCK:
  if not path.exists():
   temp=path.with_suffix('.tmp')
   r=subprocess.run([sys.executable,str(ROOT/'sphinx_render.py'),'render',id,language,str(temp)],capture_output=True,text=True,timeout=120)
   if r.returncode:raise RuntimeError(r.stderr[-2500:])
   if language=='ko' and STORE.catalog(d['output'])[2]!=digest:
    temp.unlink(missing_ok=True);return rendered(id,language)
   temp.replace(path)
 return path.read_bytes()
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(PUBLIC),**kwargs)
 def json(self,data,status=200):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def end_headers(self):
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
  self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
  super().end_headers()
 def authenticated(self):
  cookie=SimpleCookie()
  try:cookie.load(self.headers.get('Cookie',''));value=cookie.get('review_session');return bool(value and SESSIONS.get(value.value,0)>time.time())
  except Exception:return False
 def do_HEAD(self):
  if not self.authenticated():self.send_response(401);self.end_headers();return
  p=unquote(urlsplit(self.path).path)
  if p not in {'/','/index.html','/app.js','/workflow.js','/style.css','/frame.js','/frame.css'}:self.send_error(404);return
  super().do_HEAD()
 def do_GET(self):
  p=unquote(urlsplit(self.path).path)
  if p in {'/login','/login.js','/style.css','/frame.js','/frame.css'}:
   return self.send_file(PUBLIC/('login.html' if p=='/login' else p[1:]),'text/html; charset=utf-8' if p=='/login' else 'application/javascript' if p.endswith('.js') else 'text/css')
  if not self.authenticated():
   if p.startswith('/api/'):return self.json({'error':'로그인이 필요합니다.'},401)
   self.send_response(303);self.send_header('Location','/login');self.end_headers();return
  try:
   if p=='/api/session':return self.json({'token':TOKEN})
   if p=='/api/workflow':return self.json(WORKFLOW.statuses())
   if p=='/api/documents':return self.json(STORE.manifest)
   m=re.fullmatch(r'/api/(document|revision)/([0-9a-f]{20})',p)
   if m:
    action,id=m.groups()
    if action=='revision':return self.json({'sha256':STORE.catalog(STORE.docs[id]['output'])[2]})
    return self.json(STORE.document(id))
   m=re.fullmatch(r'/render/([0-9a-f]{20})/(en|ko)',p)
   if m:
    raw=rendered(*m.groups());self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
   if p=='/translation-review-checklist.xlsx':
    return self.send_file(RUN/'translation-review-checklist.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
   if p.startswith('/assets/'):
    bits=p.split('/',3)
    if len(bits)!=4 or bits[2] not in {'sdk-doc','sdk-release','skyline-doc'}:raise KeyError()
    root=(ROOT/'build'/bits[2]/'en').resolve();target=(root/bits[3]).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix.lower() not in {'.png','.jpg','.jpeg','.gif','.svg','.webp','.css','.woff','.woff2'}:raise KeyError()
    return self.send_file(target,self.guess_type(str(target)))
   if p not in {'/','/index.html','/app.js','/workflow.js','/style.css','/frame.js','/frame.css'}:raise KeyError()
   super().do_GET()
  except KeyError:self.send_error(404)
  except Conflict as e:self.json({'error':str(e)},409)
  except Exception as e:self.json({'error':'문서 처리 실패: '+str(e)},500)
 def send_file(self,p,mime):
  raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_POST(self):
  if urlsplit(self.path).path=='/api/login':return self.login()
  if not self.authenticated():return self.json({'error':'로그인이 필요합니다.'},401)
  if self.headers.get('Origin')!=ORIGIN or self.headers.get('Host')!=f'127.0.0.1:{PORT}' or not hmac.compare_digest(self.headers.get('X-Review-Token',''),TOKEN):return self.json({'error':'이 검토 페이지에서 요청을 다시 보내 주세요.'},403)
  action=urlsplit(self.path).path
  if action not in {'/api/save','/api/approve','/api/remote-refresh','/api/upload-preview','/api/upload'}:return self.json({'error':'경로 없음'},404)
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=1000000:raise Invalid('요청 크기가 올바르지 않습니다.')
   data=json.loads(self.rfile.read(n))
   if action=='/api/approve':
    if type(data.get('approved')) is not bool:raise Invalid('승인 값을 확인해 주세요.')
    return self.json(WORKFLOW.approve(data['documents'],data['approved']))
   if action=='/api/remote-refresh':return self.json(WORKFLOW.start_refresh())
   if action=='/api/upload-preview':return self.json(WORKFLOW.preview(data['documents']))
   if action=='/api/upload':return self.json(WORKFLOW.upload(data['ticket']))
   id=data['document'];index=data['index']
   if not isinstance(index,int) or isinstance(index,bool):raise Invalid('항목 번호가 올바르지 않습니다.')
   result=STORE.save(id,index,data['previous'],data['translation']);return self.json(result)
  except Conflict as e:return self.json({'error':str(e)},409)
  except (Invalid,ValueError,KeyError,TypeError) as e:return self.json({'error':str(e)},400)
  except Exception as e:return self.json({'error':'저장 실패: '+str(e)},500)
 def login(self):
  if self.headers.get('Origin')!=ORIGIN or self.headers.get('Host')!=f'127.0.0.1:{PORT}':return self.json({'error':'검토 페이지에서 로그인해 주세요.'},403)
  address=self.client_address[0];now=time.time();attempts=[t for t in LOGIN_ATTEMPTS.get(address,[]) if now-t<60];LOGIN_ATTEMPTS[address]=attempts
  if len(attempts)>=10:return self.json({'error':'잠시 후 다시 시도해 주세요.'},429)
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=4096:raise ValueError()
   supplied=json.loads(self.rfile.read(n))['key']
   if not isinstance(supplied,str):raise ValueError()
   valid=hmac.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(),AUTH['key_sha256'])
  except Exception:valid=False
  if not valid:
   attempts.append(now);return self.json({'error':'접속키를 확인해 주세요.'},403)
  session=secrets.token_urlsafe(32);SESSIONS[session]=now+43200
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Set-Cookie',f'review_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200');self.end_headers();self.wfile.write(b'{"ok":true}')
 def list_directory(self,path):self.send_error(404)
if __name__=='__main__':
 def refresh_loop():
  while True:
   try:WORKFLOW.start_refresh()
   except Exception:pass
   time.sleep(300)
 if os.environ.get('REVIEW_REMOTE_REFRESH','1')=='1':threading.Thread(target=refresh_loop,daemon=True).start()
 ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
