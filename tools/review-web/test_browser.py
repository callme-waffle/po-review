"""Exercise the deployed review app through installed Chromium's DevTools protocol."""
import subprocess,tempfile,pathlib,time,json,urllib.request,socket,base64,os,struct,hashlib
CHROME='/home/codex/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome'
BASE='http://127.0.0.1:8080'
class CDP:
 def __init__(self,url):
  from urllib.parse import urlsplit
  u=urlsplit(url);self.sock=socket.create_connection((u.hostname,u.port),10);self.seq=0
  key=base64.b64encode(os.urandom(16)).decode()
  self.sock.sendall(f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
  response=b''
  while not response.endswith(b'\r\n\r\n'):response+=self.sock.recv(1)
  assert response.startswith(b'HTTP/1.1 101 '),response
 def read(self,n):
  data=b''
  while len(data)<n:
   chunk=self.sock.recv(n-len(data))
   if not chunk:raise EOFError()
   data+=chunk
  return data
 def call(self,method,params=None,session_id=None):
  self.seq+=1;raw=json.dumps({'id':self.seq,'method':method,'params':params or {},**({'sessionId':session_id} if session_id else {})}).encode();mask=os.urandom(4);n=len(raw)
  header=bytes([0x81,0x80|(n if n<126 else 126 if n<65536 else 127)])
  if n>=126:header+=struct.pack('!H' if n<65536 else '!Q',n)
  self.sock.sendall(header+mask+bytes(v^mask[i%4] for i,v in enumerate(raw)))
  while True:
   a,b=self.read(2);n=b&127
   if n==126:n=struct.unpack('!H',self.read(2))[0]
   elif n==127:n=struct.unpack('!Q',self.read(8))[0]
   data=self.read(n)
   if a&15!=1:continue
   msg=json.loads(data)
   if msg.get('id')==self.seq:
    assert 'error' not in msg,msg
    return msg['result']
 def evaluate(self,expr):
  r=self.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':True})
  assert 'exceptionDetails' not in r,r
  return r['result'].get('value')
 def wait(self,expr):
  for _ in range(80):
   if self.evaluate(expr):return
   time.sleep(.1)
  raise AssertionError(expr)
def main():
 with tempfile.TemporaryDirectory(prefix='ossca-browser-') as tmp:
  log=open('/tmp/ossca-browser-test.log','w')
  proc=subprocess.Popen([CHROME,'--headless','--no-sandbox','--no-proxy-server','--disable-dev-shm-usage','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+tmp,'about:blank'],stdout=log,stderr=log)
  try:
   portfile=pathlib.Path(tmp)/'DevToolsActivePort'
   for _ in range(100):
    if portfile.exists():break
    time.sleep(.1)
   port=int(portfile.read_text().splitlines()[0]);targets=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
   c=CDP(next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page'))
   c.call('Page.enable');c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1080,'deviceScaleFactor':1,'mobile':False})
   c.call('Page.navigate',{'url':BASE});c.wait("document.querySelectorAll('.entry').length > 0")
   assert c.evaluate("document.querySelectorAll('.doc-link').length")==417
   assert c.evaluate("document.getElementById('error').hidden")
   c.evaluate("document.getElementById('priority').value='0';document.getElementById('priority').dispatchEvent(new Event('input'))")
   assert c.evaluate("document.querySelectorAll('.doc-link').length")==55
   c.evaluate("document.getElementById('project').value='skyline-apiserver';document.getElementById('project').dispatchEvent(new Event('input'))")
   assert c.evaluate("document.querySelectorAll('.doc-link').length")==10
   c.evaluate("document.querySelector('.doc-link').click()")
   c.wait("document.getElementById('doc-project').textContent.includes('skyline-apiserver')")
   c.evaluate("document.getElementById('project').value='';document.getElementById('priority').value='';document.getElementById('doc-search').value='proxies/network.rst';document.getElementById('doc-search').dispatchEvent(new Event('input'))")
   assert c.evaluate("document.querySelectorAll('.doc-link').length")==1
   c.evaluate("document.querySelector('.doc-link').click()")
   c.wait("document.getElementById('doc-path').textContent.includes('proxies/network.rst')")
   assert c.evaluate("document.querySelectorAll('.entry').length")==40
   c.evaluate("document.getElementById('next').click()")
   assert c.evaluate("document.getElementById('page-count').textContent.startsWith('2 /')")
   c.evaluate("document.getElementById('entry-search').value='network';document.getElementById('entry-search').dispatchEvent(new Event('input'))")
   assert c.evaluate("document.querySelectorAll('mark').length>0")
   c.evaluate("document.getElementById('entry-search').value='unmatchable-8d98ddf';document.getElementById('entry-search').dispatchEvent(new Event('input'))")
   assert c.evaluate("document.querySelectorAll('.entry').length")==0
   c.evaluate("document.getElementById('entry-search').value='';document.getElementById('entry-search').dispatchEvent(new Event('input'));document.querySelector('.entry-meta a').click()")
   c.wait("location.hash.includes('entry=')")
   c.call('Page.reload');c.wait("document.querySelectorAll('.entry').length>0")
   assert c.evaluate("document.getElementById('doc-path').textContent.includes('proxies/network.rst')")
   c.evaluate('window.scrollTo(0,0)')
   screenshot=c.call('Page.captureScreenshot',{'format':'png'})
   pathlib.Path('/workspace/po-review/output/translation-review-web.png').write_bytes(base64.b64decode(screenshot['data']))
   c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
   assert c.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'mobile overflow'
   print(json.dumps({'browser':'Chromium','documents':417,'previous_filter':55,'skyline_filter':10,'document_search':True,'paired_text':True,'pagination':True,'entry_search':True,'deep_link_reload':True,'mobile_no_horizontal_overflow':True}))
  finally:
   proc.terminate()
   try:proc.wait(timeout=8)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
   log.close()
if __name__=='__main__':main()
