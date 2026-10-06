#!/usr/bin/env python3
"""Integration checks for workbook integrity and preservation of human review edits."""
import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
from xml.etree import ElementTree as E
spec=importlib.util.spec_from_file_location('builder',Path(__file__).with_name('build_review_checklist.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
NS={'m':b.N}
class WorkbookTests(unittest.TestCase):
 def test_real_input_structure(self):
  path=Path('/workspace/po-review/output/translation-review-checklist.xlsx')
  if not path.exists():self.skipTest('Production file not created yet')
  b.validate_package(path)
  with zipfile.ZipFile(path) as z:
   book=E.fromstring(z.read('xl/workbook.xml'))
   self.assertEqual([s.get('name') for s in book.find('m:sheets',NS)],['요약','문서별 검토','원문 이슈','용어 예외','사용 안내'])
   doc=E.fromstring(z.read('xl/worksheets/sheet2.xml'))
   self.assertEqual(doc.find('m:cols/m:col',NS).get('hidden'),'1')
   self.assertEqual(doc.find('m:sheetViews/m:sheetView/m:pane',NS).get('xSplit'),'5')
   validation=doc.find('m:dataValidations/m:dataValidation',NS)
   self.assertTrue(validation.get('sqref').startswith('H2:'))
   self.assertEqual(validation.find('m:formula1',NS).text,'"미검토,검토중,수정요청,승인,보류"')
  reviews=b.read_existing(path)['문서별 검토']
  source=json.loads(Path('/workspace/po-review/output/translation-review-data.json').read_text())
  self.assertEqual(len(reviews),len(source['documents']))
  self.assertTrue(all(r['검토 상태'] in b.STATES for r in reviews.values()))
 def test_preserve_review_and_null_and_formula_safety(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);data={'documents':[{'project':'SDK','po':'doc-user.po','source':'a.rst','priority':2,'total':3,'translated':3,'summary':'=HYPERLINK("https://invalid")'},{'project':'SDK','po':'doc-user.po','source':'b.rst','priority':3,'total':None,'translated':None}], 'catalogs':[{'project':'SDK','po':'doc-user.po','total':3,'translated':3}], 'source_issues':[{'project':'SDK','po':'doc-user.po','source':'a.rst','msgid':'issue'}]}
   inp=p/'data.json';out=p/'review.xlsx';inp.write_text(json.dumps(data))
   b.build(inp,out)
   self.assertTrue(all(r['검토 상태']=='미검토' for r in b.read_existing(out)['문서별 검토'].values()))
   with zipfile.ZipFile(out) as z:parts={n:z.read(n) for n in z.namelist()}
   root=E.fromstring(parts['xl/worksheets/sheet2.xml'])
   changes={'H2':'승인','I2':'검토자 A','J2':46296,'K2':'=SUM(1,2)'}
   for address,value in changes.items():
    c=root.find(f'.//m:c[@r="{address}"]',NS)
    for child in list(c):c.remove(child)
    if isinstance(value,int):c.set('t','n');b.sub(c,'v',v=value)
    else:c.set('t','inlineStr');b.sub(b.sub(c,'is'),'t',v=value)
   # Emulate Excel's conversion to shared strings for the reviewer name.
   name=root.find('.//m:c[@r="I2"]',NS)
   for child in list(name):name.remove(child)
   name.set('t','s');b.sub(name,'v',v=0)
   shared=E.Element('{'+b.N+'}sst',{'count':'1','uniqueCount':'1'});b.sub(b.sub(shared,'si'),'t',v='검토자 A')
   parts['xl/sharedStrings.xml']=b.xml(shared)
   parts['xl/worksheets/sheet2.xml']=b.xml(root)
   with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name,content in parts.items():z.writestr(name,content)
   data['documents'].reverse();data['documents'].append({'project':'SDK','po':'doc-user.po','source':'c.rst','priority':1,'total':1,'translated':0});inp.write_text(json.dumps(data))
   result=b.build(inp,out)
   self.assertEqual(result['preserved_reviews'],2)
   self.assertTrue(Path(result['backup']).exists())
   reviews=b.read_existing(out)['문서별 검토']
   self.assertEqual(reviews['SDK|doc-user.po|a.rst'],dict(zip(b.FIELDS,['승인','검토자 A',46296,'=SUM(1,2)'])))
   self.assertEqual(reviews['SDK|doc-user.po|c.rst']['검토 상태'],'미검토')
   with zipfile.ZipFile(out) as z:
    root=E.fromstring(z.read('xl/worksheets/sheet2.xml'))
    self.assertEqual(root.find('.//m:c[@r="K3"]',NS).get('t'),'inlineStr')
    self.assertEqual(root.find('.//m:c[@r="G4"]/m:is/m:t',NS).text,'집계 중')
    self.assertIsNone(root.find('.//m:c[@r="L4"]/m:v',NS))
    summary=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
    self.assertEqual(summary.find('.//m:c[@r="J2"]/m:v',NS).text,'1')
    self.assertIn('$H$',summary.find('.//m:c[@r="J2"]/m:f',NS).text)
if __name__=='__main__':unittest.main(verbosity=2)
