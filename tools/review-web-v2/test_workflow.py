import unittest,tempfile,json,threading
from pathlib import Path
from io import BytesIO
from babel.messages.catalog import Catalog
from babel.messages.pofile import write_po,read_po
from workflow import Workflow,values,key
from store import Store,Conflict,Invalid

def po(items):
 c=Catalog(locale='ko_KR')
 for src,target in items.items():c.add(src,target)
 b=BytesIO();write_po(b,c);return b.getvalue()
class FakeRemote:
 def __init__(self):self.raw=po({'A':'원격 A','B':'원격 B','Shared':'공유'});self.uploads=[];self.fail=False;self.skip=False
 def fetch(self,*a):
  if self.fail:raise Invalid('오프라인')
  return self.raw
 def upload(self,p,n,raw):
  self.uploads.append(raw)
  if not self.skip:
   c={m.id:m.string for m in read_po(BytesIO(self.raw)) if m.id};c.update({m.id:m.string for m in read_po(BytesIO(raw)) if m.id});self.raw=po(c)
  return {'accepted':1}
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.file=self.root/'doc.po';self.file.write_bytes(po({'A':'로컬 A','B':'로컬 B','Shared':'공유'}))
  messages=list(read_po(BytesIO(self.file.read_bytes())));docs=[]
  for id,sources in [('a',['A','Shared']),('b',['B','Shared'])]:
   d={'id':id,'project':'openstacksdk','po':'doc.po','output':str(self.file),'source':id+'.rst'};docs.append(d)
   (self.root/(id+'.json')).write_text(json.dumps({'entries':[{'index':i,'source':m.id,'context':m.context} for i,m in enumerate(messages) if m.id in sources]}))
  (self.root/'manifest.json').write_text(json.dumps({'documents':docs}));self.s=Store(self.root/'manifest.json',self.root,self.root/'history');self.r=FakeRemote();self.w=Workflow(self.s,self.r);self.w.refresh_group('openstacksdk|doc.po')
 def tearDown(self):self.w.db.close();self.tmp.cleanup()
 def item(self,id):return {'id':id,'revision':self.w.status(id)['revision']}
 def approved(self,id):self.w.approve([self.item(id)])
 def plan(self,id):
  ticket=self.w.preview([self.item(id)])['ticket'];return self.w.plans[ticket]
 def test_partial_upload_preserves_unselected(self):
  self.approved('a');result=self.w.execute(self.plan('a'));self.assertTrue(result[0]['ok']);self.assertEqual(set(values(self.r.uploads[0])),{json.dumps([None,'A'])});self.assertEqual(self.w.status('a')['remote'],'synced');self.assertEqual(self.w.status('b')['remote'],'pending');self.assertFalse(self.w.status('b')['approved'])
 def test_edit_invalidates_only_affected_approval_and_persists(self):
  self.approved('a');self.approved('b');self.file.write_bytes(po({'A':'새 값','B':'로컬 B','Shared':'공유'}));self.assertEqual(self.w.status('a')['approval'],'stale');self.assertTrue(self.w.status('b')['approved']);w=Workflow(self.s,self.r);self.assertTrue(w.status('b')['approved']);w.db.close()
 def test_shared_entries_require_all_approvals(self):
  self.file.write_bytes(po({'A':'로컬 A','B':'로컬 B','Shared':'공유 수정'}));self.approved('a')
  with self.assertRaises(Invalid):self.plan('a')
  self.approved('b');self.assertEqual(len(self.plan('a')['revisions']),2)
 def test_stale_approval_and_preview_rejected(self):
  self.approved('a');plan=self.plan('a');old=self.item('a');self.file.write_bytes(po({'A':'새 값','B':'로컬 B','Shared':'공유'}))
  with self.assertRaises(Conflict):self.w.approve([old])
  with self.assertRaises(Conflict):self.w.execute(plan)
  self.assertEqual(self.r.uploads,[])
 def test_remote_conflict_blocks_upload(self):
  self.approved('a');plan=self.plan('a');self.r.raw=po({'A':'다른 사람 수정','B':'원격 B','Shared':'공유'});result=self.w.execute(plan);self.assertFalse(result[0]['ok']);self.assertFalse(self.r.uploads)
 def test_remote_approved_skip_and_failure_stay_pending(self):
  self.approved('a');self.r.skip=True;result=self.w.execute(self.plan('a'));self.assertFalse(result[0]['ok']);self.assertEqual(self.w.status('a')['remote'],'pending');self.r.fail=True;self.w.refresh_group('openstacksdk|doc.po');self.assertEqual(self.w.status('a')['remote'],'error');self.assertTrue(self.w.status('a')['approved'])
 def test_no_approval_no_upload(self):
  with self.assertRaises(Invalid):self.plan('a')
  self.assertFalse(self.r.uploads)
if __name__=='__main__':unittest.main(verbosity=2)
