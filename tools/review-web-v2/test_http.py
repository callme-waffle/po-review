import urllib.request,urllib.error,http.cookiejar,json,re,time
from pathlib import Path
import os
BASE=os.environ.get('REVIEW_TEST_URL','http://127.0.0.1:8081')
key=re.search(r'접속키: (.+)',Path('/workspace/po-review/output/translation-review-access.txt').read_text()).group(1)
for path in ['/api/documents','/api/session']:
 try:urllib.request.urlopen(BASE+path);raise AssertionError('unauthenticated access')
 except urllib.error.HTTPError as e:assert e.code==401
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def request(path,data=None,extra=None):
 headers={'Origin':BASE,**(extra or {})}
 if data is not None:headers['Content-Type']='application/json'
 req=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
 return client.open(req,timeout=120)
with request('/api/login',{'key':key}) as r:assert json.load(r)['ok']
with request('/api/documents') as r:m=json.load(r)
with request('/api/session') as r:token=json.load(r)['token']
assert len(m['documents'])==417
cats={}
for d in m['documents']:cats.setdefault((d['project'],d['po']),d)
for group,d in cats.items():
 for lang in ['en','ko']:
  start=time.monotonic()
  with request('/render/'+d['id']+'/'+lang) as r:html=r.read().decode()
  assert 'data-entry=' in html,(group,lang)
  assert 'data-language="'+lang+'"' in html
  print(json.dumps({'catalog':list(group),'language':lang,'seconds':round(time.monotonic()-start,2),'entry_markers':html.count('data-entry=')},ensure_ascii=False),flush=True)
d=next(d for d in m['documents'] if d['project']=='openstacksdk' and d['po']=='doc-install.po')
with request('/api/document/'+d['id']) as r:doc=json.load(r)
e=doc['entries'][0];payload={'document':d['id'],'index':e['index'],'previous':e['translation'],'translation':e['translation']}
try:request('/api/save',payload);raise AssertionError('csrf')
except urllib.error.HTTPError as x:assert x.code==403
with request('/api/save',payload,{'X-Review-Token':token}) as r:assert json.load(r)['changed'] is False
for path in ['/access.json','/history/','/../server.py']:
 try:request(path);raise AssertionError(path)
 except urllib.error.HTTPError as e:assert e.code==404
print('AUTH, CSRF, SAFE NOOP, PRIVATE FILES: PASS')
