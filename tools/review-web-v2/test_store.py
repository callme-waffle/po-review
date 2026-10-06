import unittest,tempfile,json,concurrent.futures
from pathlib import Path
from io import BytesIO
from babel.messages.pofile import read_po
from store import Store,Conflict,Invalid
PO='''msgid ""
msgstr ""
"Project-Id-Version: test\\n"
"Language: ko\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"

#. keep this comment
#: original.rst:0
msgid "Installation"
msgstr "설치"

#: original.rst:3
msgid "Use ``pip``."
msgstr "``pip``\\\\ 를 사용합니다."

#: original.rst:5
msgid "More details"
msgstr "자세한 내용"
'''
class StoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.po=self.root/'test.po';self.po.write_text(PO)
  self.id='a'*20;messages=list(read_po(BytesIO(self.po.read_bytes())))
  doc={'id':self.id,'source':'doc/source/install.rst','output':str(self.po),'total':3}
  (self.root/'manifest.json').write_text(json.dumps({'documents':[doc]}))
  (self.root/(self.id+'.json')).write_text(json.dumps({**doc,'entries':[{'index':i,'source':m.id,'translation':m.string,'context':m.context} for i,m in enumerate(messages) if m.id]}))
  self.store=Store(self.root/'manifest.json',self.root,self.root/'history')
 def tearDown(self):self.tmp.cleanup()
 def test_save_preserves_other_bytes_and_locations_and_backup(self):
  before=self.po.read_bytes();r=self.store.save(self.id,1,'설치','설치 "안내"\n\n추가 안내입니다.')
  self.assertTrue(r['changed']);after=self.po.read_bytes();self.assertIn(b'#: original.rst:0',after)
  self.assertEqual(after.split(b'#: original.rst:3')[1],before.split(b'#: original.rst:3')[1]);self.assertEqual(Path(r['backup']).read_bytes(),before)
  self.assertEqual(self.store.document(self.id)['entries'][0]['translation'],'설치 "안내"\n\n추가 안내입니다.')
 def test_conflict_and_validation_leave_po_unchanged(self):
  before=self.po.read_bytes()
  with self.assertRaises(Conflict):self.store.save(self.id,1,'오래된 값','설치 안내')
  old=self.store.document(self.id)['entries'][1]['translation']
  with self.assertRaises(Invalid):self.store.save(self.id,2,old,'pip를 사용합니다.')
  with self.assertRaises(Invalid):self.store.save(self.id,1,'설치','.. include:: /etc/passwd')
  self.assertEqual(self.po.read_bytes(),before)
 def test_same_entry_concurrent_edit_conflicts(self):
  def save(value):
   try:self.store.save(self.id,1,'설치',value);return 'saved'
   except Conflict:return 'conflict'
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,['설치 안내','설치 방법']))
  self.assertCountEqual(results,['saved','conflict'])
 def test_external_change_and_noop(self):
  self.assertFalse(self.store.save(self.id,1,'설치','설치')['changed'])
  self.po.write_text(PO.replace('msgstr "설치"','msgstr "외부 수정"'))
  self.assertEqual(self.store.document(self.id)['entries'][0]['translation'],'외부 수정')
if __name__=='__main__':unittest.main(verbosity=2)
