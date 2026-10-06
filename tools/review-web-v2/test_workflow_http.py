import unittest,json,time,threading,http.client
from http.server import ThreadingHTTPServer
import server
from test_workflow import Tests
class HttpTests(Tests):
 def setUp(self):
  super().setUp();server.WORKFLOW=self.w;server.STORE=self.s;server.SESSIONS['test-session']=time.time()+60
  self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start()
 def tearDown(self):self.http.shutdown();self.http.server_close();super().tearDown()
 def call(self,path,data,auth=True,csrf=True):
  conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=10)
  headers={'Host':'127.0.0.1:8080','Origin':server.ORIGIN,'Content-Type':'application/json'}
  if auth:headers['Cookie']='review_session=test-session'
  if csrf:headers['X-Review-Token']=server.TOKEN
  conn.request('POST',path,json.dumps(data),headers);r=conn.getresponse();body=json.loads(r.read());conn.close();return r.status,body
 def test_http_upload_auth_csrf_preview_and_confirm(self):
  item=self.item('a')
  self.assertEqual(self.call('/api/approve',{'documents':[item],'approved':True},auth=False)[0],401)
  self.assertEqual(self.call('/api/approve',{'documents':[item],'approved':True},csrf=False)[0],403)
  self.assertEqual(self.call('/api/approve',{'documents':[item],'approved':True})[0],200)
  code,p=self.call('/api/upload-preview',{'documents':[item]});self.assertEqual(code,200);self.assertFalse(self.r.uploads)
  self.assertEqual(self.call('/api/upload',{'ticket':p['ticket']})[0],200)
  until=time.time()+5
  while self.w.busy and time.time()<until:time.sleep(.02)
  self.assertFalse(self.w.busy);self.assertEqual(len(self.r.uploads),1);self.assertEqual(self.w.status('a')['remote'],'synced')
  self.assertEqual(self.call('/api/upload',{'ticket':p['ticket']})[0],409)
if __name__=='__main__':unittest.main(verbosity=2)
