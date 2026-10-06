"""Document approvals and explicit, partial Weblate uploads. No automatic writes."""
from pathlib import Path
from io import BytesIO
import json,hashlib,threading,uuid,time,sqlite3,sys
from datetime import datetime,timezone
from babel.messages.pofile import read_po,write_po
from babel.messages.catalog import Catalog
from store import Conflict,Invalid

def stamp():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def key(e):return json.dumps([e.get('context'),e['source']],ensure_ascii=False)
def values(raw):
 return {json.dumps([m.context,m.id],ensure_ascii=False):[m.string,'fuzzy' in m.flags] for m in read_po(BytesIO(raw)) if m.id}

class Remote:
 def __init__(self):
  sys.path.insert(0,'/opt/po-review/src/i18n/bin')
  from weblate_utils import SimpleIniConfig
  c=SimpleIniConfig(str(Path.home()/'.config/weblate'))
  if c.url.rstrip('/') not in ('https://weblate.example.invalid','https://weblate.example.invalid/api'):raise Invalid('Weblate 연결 주소를 확인해 주세요.')
  self.headers={'Authorization':'Token '+c.key} if c.key else {}
 def url(self,project,po):return f'https://weblate.example.invalid/api/translations/{project}/master%252F{Path(po).stem}/ko_KR/file/'
 def call(self,method,project,po,**kw):
  import requests
  try:r=requests.request(method,self.url(project,po),headers=self.headers,timeout=(10,90),allow_redirects=False,**kw)
  except requests.RequestException:raise Invalid('Weblate 연결 실패 또는 응답 지연입니다. 원격 상태를 다시 확인해 주세요.')
  if r.status_code not in (200,201):raise Invalid(f'Weblate HTTP {r.status_code}: 한국어 ko_KR 등록 및 API 권한을 확인해 주세요.')
  return r
 def fetch(self,project,po):return self.call('GET',project,po).content
 def upload(self,project,po,raw):
  return self.call('POST',project,po,files={'file':(po,raw,'application/x-gettext')},data={'method':'translate','conflicts':'replace-translated','fuzzy':'process'}).json()

class Workflow:
 def __init__(self,store,remote=None):
  self.store=store;self.remote=remote;self.lock=threading.RLock();self.busy=False;self.job=None;self.plans={};self.cache={}
  self.db=sqlite3.connect(store.private/'workflow.sqlite3',check_same_thread=False)
  self.db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)');self.db.commit()
  self.groups={}
  for d in store.docs.values():self.groups.setdefault(d['project']+'|'+d['po'],[]).append(d['id'])
 def get(self,k,default=None):
  if k not in self.cache:
   r=self.db.execute('SELECT value FROM state WHERE key=?',(k,)).fetchone();self.cache[k]=json.loads(r[0]) if r else default
  return self.cache[k]
 def put(self,k,v):self.cache[k]=v;self.db.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)));self.db.commit()
 def client(self):
  if self.remote is None:self.remote=Remote()
  return self.remote
 def snapshot(self,id):
  d=self.store.document(id);v={key(e):[e['translation'],e['fuzzy']] for e in d['entries']}
  return d,v,digest(v)
 def status(self,id):
  d,v,h=self.snapshot(id);a=self.get('approval:'+id);r=self.get('remote:'+d['project']+'|'+d['po']);approved=bool(a and a['revision']==h)
  state='unknown' if not r else 'error' if r.get('error') else 'synced' if all(r['values'].get(k)==val for k,val in v.items()) else 'pending'
  return {'id':id,'revision':h,'approved':approved,'approval':('approved' if approved else 'stale' if a else 'unreviewed'),'approved_at':a['time'] if approved else None,'remote':state,'checked_at':r.get('time') if r else None,'remote_error':r.get('error') if r else None}
 def statuses(self):
  with self.lock,self.store.lock:return {'documents':[self.status(id) for id in self.store.docs],'job':self.job,'busy':self.busy}
 def approve(self,items,approved=True):
  if not isinstance(items,list) or not items:raise Invalid('문서를 선택해 주세요.')
  with self.lock,self.store.lock:
   for item in items:
    if self.snapshot(item['id'])[2]!=item['revision']:raise Conflict('문서가 변경되었습니다. 다시 검토해 주세요.')
   for item in items:self.put('approval:'+item['id'],{'revision':item['revision'],'time':stamp()} if approved else None)
  return {'ok':True}
 def refresh_group(self,g):
  project,po=g.split('|')
  try:
   v=values(self.client().fetch(project,po))
   if not v:raise Invalid('원격 번역 파일에 비교할 항목이 없습니다.')
   data={'values':v,'time':stamp()}
  except Exception as e:data={'error':str(e),'time':stamp()}
  with self.lock:self.put('remote:'+g,data)
  return data
 def start_refresh(self):
  def refresh_all():
   results=[]
   for g in self.groups:
    r=self.refresh_group(g);results.append({'component':g,'ok':not bool(r.get('error')),'message':r.get('error','확인 완료')})
   return results
  return self.start_job('refresh',refresh_all)
 def start_job(self,kind,fn):
  with self.lock:
   if self.busy:raise Conflict('진행 중인 원격 작업이 있습니다.')
   self.busy=True;self.job={'kind':kind,'state':'running','started_at':stamp()}
  def run():
   try:
    result=fn()
    with self.lock:self.job.update(state='done',result=result)
   except Exception as e:
    with self.lock:self.job.update(state='failed',error=str(e))
   finally:
    with self.lock:self.busy=False;self.job['finished_at']=stamp()
  threading.Thread(target=run,daemon=True).start();return {'started':True}
 def preview(self,items):
  with self.lock,self.store.lock:
   if self.busy:raise Conflict('원격 상태 확인이 끝난 뒤 시도해 주세요.')
   if not isinstance(items,list) or not items:raise Invalid('업로드할 문서를 선택해 주세요.')
   selected={i['id']:i['revision'] for i in items};groups={};affected=set()
   for id,h in selected.items():
    d,v,actual=self.snapshot(id);s=self.status(id)
    if actual!=h:raise Conflict('선택한 문서가 변경되었습니다.')
    if not s['approved']:raise Invalid('선택한 모든 문서를 먼저 승인해 주세요.')
    g=d['project']+'|'+d['po'];r=self.get('remote:'+g)
    if not r or r.get('error'):raise Invalid('원격 상태 확인을 먼저 완료해 주세요.')
    delta={k:val for k,val in v.items() if r['values'].get(k)!=val}
    if any(k not in r['values'] for k in delta):raise Invalid('Weblate에 없는 원문이 있습니다. POT를 먼저 갱신해 주세요.')
    if any(val[1] or not val[0] for val in delta.values()):raise Invalid('비어 있거나 수정 필요 상태인 항목을 먼저 검토해 주세요.')
    groups.setdefault(g,{}).update(delta)
   groups={g:v for g,v in groups.items() if v}
   if not groups:raise Invalid('업로드할 변경 사항이 없습니다.')
   revisions={}
   for g,delta in groups.items():
    for id in self.groups[g]:
     d,v,h=self.snapshot(id)
     if set(v)&set(delta):
      affected.add(id);revisions[id]=h
      if not self.status(id)['approved']:raise Invalid('공유 문장에 영향받는 문서도 승인해 주세요: '+d['source'])
   plan={'groups':groups,'revisions':revisions,'baseline':{g:digest(self.get('remote:'+g)['values']) for g in groups},'created':time.time()}
   self.plans={k:p for k,p in self.plans.items() if time.time()-p['created']<600}
   ticket=uuid.uuid4().hex;self.plans[ticket]=plan
   return {'ticket':ticket,'documents':[{'id':id,'source':self.store.docs[id]['source'],'project':self.store.docs[id]['project']} for id in sorted(affected)],'entries':sum(map(len,groups.values())),'components':len(groups)}
 def upload(self,ticket):
  with self.lock:
   if self.busy:raise Conflict('진행 중인 원격 작업이 있습니다.')
   plan=self.plans.pop(ticket,None)
   if not plan or time.time()-plan['created']>600:raise Conflict('업로드 목록을 다시 확인해 주세요.')
   return self.start_job('upload',lambda:self.execute(plan))
 def execute(self,plan):
  results=[]
  # Validate immutable approved payloads; later edits remain pending by revision.
  with self.lock,self.store.lock:
   for id,h in plan['revisions'].items():
    if self.snapshot(id)[2]!=h or not self.status(id)['approved']:raise Conflict('승인 이후 문서가 변경되었습니다. 다시 검토해 주세요.')
  for g,delta in plan['groups'].items():
   project,po=g.split('|')
   try:
    before=values(self.client().fetch(project,po))
    if digest(before)!=plan['baseline'][g]:raise Conflict('원격 번역이 변경되었습니다. 원격 상태 확인 후 다시 검토해 주세요.')
    with self.lock,self.store.lock:
     for id in self.groups[g]:
      if id in plan['revisions'] and (self.snapshot(id)[2]!=plan['revisions'][id] or not self.status(id)['approved']):raise Conflict('승인 이후 문서가 변경되었습니다.')
    cat=Catalog(locale='ko_KR')
    for k,val in delta.items():
     context,source=json.loads(k);cat.add(source,val[0],context=context)
    buf=BytesIO();write_po(buf,cat,width=0)
    self.client().upload(project,po,buf.getvalue())
    r=self.refresh_group(g)
    ok=not r.get('error') and all(r['values'].get(k)==v for k,v in delta.items())
    results.append({'component':g,'ok':ok,'message':'원격 반영 확인' if ok else '일부 미반영 또는 확인 실패: 원격 승인 상태와 권한을 확인해 주세요.'})
   except Exception as e:
    self.refresh_group(g);results.append({'component':g,'ok':False,'message':str(e)})
  with self.lock:self.put('upload:'+uuid.uuid4().hex,{'time':stamp(),'results':results,'documents':plan['revisions']})
  return results
