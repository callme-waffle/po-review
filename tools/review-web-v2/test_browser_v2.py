import sys,pathlib,tempfile,subprocess,time,urllib.request,json,re,base64,os
sys.path.insert(0,'/workspace/po-review/tools/review-web')
from test_browser import CDP,CHROME
BASE=os.environ.get('REVIEW_TEST_URL','http://127.0.0.1:8081')
key=re.search(r'접속키: (.+)',pathlib.Path('/workspace/po-review/output/translation-review-access.txt').read_text()).group(1)
def main():
 with tempfile.TemporaryDirectory(prefix='ossca-doc-browser-') as tmp:
  log=open('/tmp/ossca-document-browser.log','w');proc=subprocess.Popen([CHROME,'--headless','--no-sandbox','--no-proxy-server','--disable-dev-shm-usage','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+tmp,'about:blank'],stdout=log,stderr=log)
  try:
   pf=pathlib.Path(tmp)/'DevToolsActivePort'
   for _ in range(100):
    if pf.exists():break
    time.sleep(.1)
   port=int(pf.read_text().splitlines()[0]);targets=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'));c=CDP(next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page'))
   c.call('Page.enable');c.call('Emulation.setDeviceMetricsOverride',{'width':1680,'height':1120,'deviceScaleFactor':1,'mobile':False});c.call('Page.navigate',{'url':BASE})
   c.wait("location.pathname==='/login' && document.readyState==='complete' && !!document.getElementById('access-key')")
   c.evaluate("document.getElementById('access-key').value="+json.dumps(key)+";document.getElementById('login-form').requestSubmit()")
   c.wait("document.querySelectorAll('.doc').length===417")
   def wait_expr(expr,seconds=70):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
     if c.evaluate(expr):return
     time.sleep(.2)
    raise AssertionError(expr)
   wait_expr("document.getElementById('status').textContent.includes('최신 번역 표시')")
   sessions={}
   def frame(lang):
    targets=c.call('Target.getTargets')['targetInfos'];target=next(t['targetId'] for t in targets if t['type']=='iframe' and '/'+lang+'?' in t['url'])
    if target not in sessions:sessions[target]=c.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
    return sessions[target]
   def feval(lang,expr):
    result=c.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},session_id=frame(lang))
    assert 'exceptionDetails' not in result,result
    return result['result'].get('value')
   assert feval('en',"document.body.textContent.includes('Installation')")
   assert feval('ko',"document.querySelectorAll('[data-entry]').length>0")
   feval('ko',"document.querySelector('[data-entry]').click()")
   c.wait("!document.getElementById('editor').hidden")
   old=c.evaluate("document.getElementById('translation-text').value")
   assert c.evaluate("document.getElementById('source-text').value")
   if os.environ.get('REVIEW_READ_ONLY'):
    assert c.evaluate("document.getElementById('translation-text').value")
    c.wait("document.getElementById('approve-document').disabled===false")
    assert c.evaluate("document.getElementById('remote-state').textContent.includes('원격')")
    c.evaluate("document.getElementById('upload-open').click()")
    c.wait("document.getElementById('upload-dialog').open")
    assert c.evaluate("document.getElementById('upload-confirm').disabled")
    c.evaluate("document.getElementById('upload-close').click()")
    print(json.dumps({'workflow_dialog':True,'production_url':BASE,'login':True,'left_original_right_translation':True,'click_to_edit':True,'writes_performed':False}));return
   new=old+' — 화면 검증'
   c.evaluate("document.getElementById('translation-text').value="+json.dumps(new)+";document.getElementById('translation-text').dispatchEvent(new Event('input'));document.getElementById('save').click()")
   wait_expr("document.getElementById('status').textContent.includes('최신 번역 표시') && !document.getElementById('save').disabled")
   # Wait until the new iframe itself contains the saved text.
   until=time.monotonic()+40
   while time.monotonic()<until:
    try:
     if feval('ko','document.body.textContent.includes('+json.dumps(new)+')'):break
    except (AssertionError,StopIteration):pass
    time.sleep(.2)
   else:raise AssertionError('saved document not updated')
   assert not feval('en','document.body.textContent.includes('+json.dumps(new)+')')
   # Change the TEST COPY through SSH, then ensure polling refreshes the open page.
   remote="from pathlib import Path\nimport sys\nsys.path.insert(0,'/opt/po-review/work/translation-support/20261001-expansion/review-web-v2')\nfrom store import Store\nr=Path('/opt/po-review/work/translation-support/20261001-expansion/review-web-v2')\ns=Store(r/'test-fixtures/manifest.json',r.parent/'review-web/public/data',r/'test-fixtures/external-history')\nd=next(x for x in s.docs.values() if x['project']=='openstacksdk' and x['po']=='doc-install.po')\ne=s.document(d['id'])['entries'][0]\ns.save(d['id'],e['index'],e['translation'],"+repr(old+' — 외부 수정 검증')+")\n"
   subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/tmp/po-review-known-hosts','-i','/tmp/po-review-auth/id_ed25519','review@127.0.0.1','/opt/po-review/venv/bin/python','-'],input=remote,text=True,check=True,capture_output=True)
   until=time.monotonic()+40
   while time.monotonic()<until:
    try:
     if feval('ko',"document.body.textContent.includes('외부 수정 검증')"):break
    except (AssertionError,StopIteration):pass
    time.sleep(.3)
   else:raise AssertionError('external edit not refreshed')
   # Restore the test copy through the same UI, then check protection against raw directives.
   c.evaluate("document.getElementById('translation-text').value="+json.dumps(old)+";document.getElementById('translation-text').dispatchEvent(new Event('input'));document.getElementById('save').click()")
   wait_expr("!document.getElementById('save').disabled")
   c.evaluate("document.getElementById('translation-text').value='.. include:: /etc/passwd';document.getElementById('translation-text').dispatchEvent(new Event('input'));document.getElementById('save').click()")
   wait_expr("!document.getElementById('error').hidden")
   assert c.evaluate("document.getElementById('error').textContent.includes('지시문')")
   c.evaluate("document.getElementById('translation-text').value="+json.dumps(old)+";document.getElementById('translation-text').dispatchEvent(new Event('input'));document.getElementById('close-editor').click()")
   c.evaluate("document.getElementById('priority').value='0';document.getElementById('priority').dispatchEvent(new Event('input'))")
   assert c.evaluate("document.querySelectorAll('.doc').length")==55
   c.evaluate("document.getElementById('priority').value='';document.getElementById('doc-search').value='user/config/configuration.rst';document.getElementById('doc-search').dispatchEvent(new Event('input'));document.querySelector('.doc').click()")
   wait_expr("document.getElementById('path').textContent.includes('config/configuration.rst') && document.getElementById('status').textContent.includes('최신 번역 표시')")
   assert feval('en',"document.querySelector('h1')!==null")
   assert feval('ko',"document.querySelector('h1')!==null")
   screenshot=c.call('Page.captureScreenshot',{'format':'png'});pathlib.Path('/workspace/po-review/output/translation-document-review.png').write_bytes(base64.b64decode(screenshot['data']))
   print(json.dumps({'login':True,'documents':417,'previous_filter':55,'rendered_documents':True,'click_to_edit':True,'save_updates_document':True,'english_unchanged':True,'external_change_auto_refresh':True,'invalid_rst_rejected':True,'test_po_only':True}))
  except Exception:
   print('BROWSER DIAGNOSTIC',c.evaluate('JSON.stringify({url:location.href,text:document.body.innerText.slice(0,1800)})'))
   raise
  finally:
   proc.terminate()
   try:proc.wait(timeout=8)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
   log.close()
if __name__=='__main__':main()
