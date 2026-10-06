#!/usr/bin/env python3
"""Build a Korean review XLSX with stdlib. Preserve human reviews by stable ID."""
import argparse, collections, datetime as dt, hashlib, json, os, posixpath, re, shutil, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as E
N='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
KST=dt.timezone(dt.timedelta(hours=9))
STATES=['미검토','검토중','수정요청','승인','보류']
FIELDS=['검토 상태','검토자','검토일','검토 메모']
E.register_namespace('',N);E.register_namespace('r',R)
def text(v):
 if v is None:return ''
 if isinstance(v,bool):return '있음' if v else '없음'
 if isinstance(v,(list,dict)):v=json.dumps(v,ensure_ascii=False)
 return re.sub('[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]','',str(v))[:32767]
def sub(p,t,a=None,v=None):
 e=E.SubElement(p,'{'+N+'}'+t,a or {})
 if v is not None:e.text=text(v)
 return e
def xml(e):return E.tostring(e,encoding='utf-8',xml_declaration=True)
def col(n):
 s=''
 while n:n,r=divmod(n-1,26);s=chr(65+r)+s
 return s
def formula(f,v=0,s=6):return {'formula':f,'cache':v,'style':s}
def cell(row,r,c,v,s=7):
 if isinstance(v,dict):s=v.get('style',s)
 e=sub(row,'c',{'r':f'{col(c)}{r}','s':str(s)})
 if isinstance(v,dict) and 'formula' in v:sub(e,'f',v=v['formula']);sub(e,'v',v=v.get('cache',0))
 elif isinstance(v,(int,float)) and not isinstance(v,bool):e.set('t','n');sub(e,'v',v=v)
 else:
  e.set('t','inlineStr');t=sub(sub(e,'is'),'t',v=text(v));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
def sheet(headers,rows,widths,edit=(),status=None,percent=(),hidden=False,height=60,freeze_cols=0):
 root=E.Element('{'+N+'}worksheet');last=max(1,len(rows)+1)
 sub(root,'dimension',{'ref':f'A1:{col(len(headers))}{last}'})
 v=sub(sub(root,'sheetViews'),'sheetView',{'workbookViewId':'0'})
 pane={'ySplit':'1','topLeftCell':f'{col(freeze_cols+1)}2','activePane':'bottomRight' if freeze_cols else 'bottomLeft','state':'frozen'}
 if freeze_cols:pane['xSplit']=str(freeze_cols)
 sub(v,'pane',pane)
 active=f'{col(freeze_cols+1)}2'
 sub(v,'selection',{'pane':pane['activePane'],'activeCell':active,'sqref':active})
 sub(root,'sheetFormatPr',{'defaultRowHeight':'18'});cols=sub(root,'cols')
 for n,w in enumerate(widths,1):
  a={'min':str(n),'max':str(n),'width':str(w),'customWidth':'1'}
  if hidden and n==1:a['hidden']='1'
  sub(cols,'col',a)
 data=sub(root,'sheetData');h=sub(data,'row',{'r':'1','ht':'32','customHeight':'1'})
 for n,x in enumerate(headers,1):cell(h,1,n,x,1)
 for r,values in enumerate(rows,2):
  row=sub(data,'row',{'r':str(r),'ht':str(height),'customHeight':'1'})
  for c,v in enumerate(values,1):
   style=3 if c in edit else 7
   if c in percent:style=5
   elif isinstance(v,(int,float)):style=4 if c in edit and headers[c-1]=='검토일' else 6
   cell(row,r,c,v,style)
 sub(root,'autoFilter',{'ref':f'A1:{col(len(headers))}{last}'})
 if status and rows:
  cf=sub(root,'conditionalFormatting',{'sqref':f'{col(status)}2:{col(status)}{last}'})
  for n,state in enumerate(STATES):sub(sub(cf,'cfRule',{'type':'cellIs','dxfId':str(n),'priority':str(n+1),'operator':'equal'}),'formula',v='"'+state+'"')
  d=sub(sub(root,'dataValidations',{'count':'1'}),'dataValidation',{'type':'list','allowBlank':'0','showErrorMessage':'1','showInputMessage':'1','errorTitle':'검토 상태 확인','error':'목록의 검토 상태를 선택합니다.','promptTitle':'사람의 검토 결과','prompt':'번역 완료만으로 승인하지 않습니다.','sqref':f'{col(status)}2:{col(status)}{last}'})
  sub(d,'formula1',v='"'+','.join(STATES)+'"')
 sub(root,'pageMargins',{'left':'0.25','right':'0.25','top':'0.5','bottom':'0.5','header':'0.2','footer':'0.2'})
 return xml(root)
def styles():
 root=E.Element('{'+N+'}styleSheet');fonts=sub(root,'fonts',{'count':'2'})
 for bold,color in [(False,'FF243746'),(True,'FFFFFFFF')]:
  f=sub(fonts,'font')
  if bold:sub(f,'b')
  sub(f,'sz',{'val':'10'});sub(f,'color',{'rgb':color});sub(f,'name',{'val':'맑은 고딕'});sub(f,'family',{'val':'2'})
 fills=sub(root,'fills',{'count':'4'})
 for pattern,color in [('none',None),('gray125',None),('solid','FF244E67'),('solid','FFFFF2CC')]:
  p=sub(sub(fills,'fill'),'patternFill',{'patternType':pattern})
  if color:sub(p,'fgColor',{'rgb':color});sub(p,'bgColor',{'indexed':'64'})
 borders=sub(root,'borders',{'count':'2'})
 for colored in [False,True]:
  b=sub(borders,'border')
  for side in ['left','right','top','bottom','diagonal']:
   edge=sub(b,side,{'style':'thin'} if colored and side!='diagonal' else {})
   if colored and side!='diagonal':sub(edge,'color',{'rgb':'FFDDE5EB'})
 sub(sub(root,'cellStyleXfs',{'count':'1'}),'xf',{'numFmtId':'0','fontId':'0','fillId':'0','borderId':'0'})
 xfs=sub(root,'cellXfs',{'count':'8'})
 for font,fill,fmt,wrap in [(0,0,0,0),(1,2,0,1),(0,0,0,1),(0,3,0,1),(0,3,14,1),(0,0,10,1),(0,0,0,1),(0,0,0,1)]:
  x=sub(xfs,'xf',{'numFmtId':str(fmt),'fontId':str(font),'fillId':str(fill),'borderId':'1','xfId':'0','applyAlignment':'1','applyNumberFormat':'1'})
  sub(x,'alignment',{'vertical':'top','wrapText':str(wrap)})
 sub(sub(root,'cellStyles',{'count':'1'}),'cellStyle',{'name':'Normal','xfId':'0','builtinId':'0'})
 dx=sub(root,'dxfs',{'count':'5'})
 for color in ['FFF0F2F4','FFDDEBFF','FFFFD9D9','FFDDF1DA','FFE8DEEF']:
  p=sub(sub(sub(dx,'dxf'),'fill'),'patternFill',{'patternType':'solid'});sub(p,'fgColor',{'rgb':color});sub(p,'bgColor',{'indexed':'64'})
 sub(root,'tableStyles',{'count':'0','defaultTableStyle':'TableStyleMedium2','defaultPivotStyle':'PivotStyleLight16'})
 return xml(root)
def read_existing(path):
 if not path or not Path(path).exists():return {}
 result={};ns={'m':N}
 with zipfile.ZipFile(path) as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():shared=[''.join(si.itertext()) for si in E.fromstring(z.read('xl/sharedStrings.xml'))]
  rels={r.attrib['Id']:r.attrib['Target'] for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
  for s in E.fromstring(z.read('xl/workbook.xml')).find('m:sheets',ns):
   target=rels[s.attrib['{'+R+'}id']];target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
   rows=[]
   for row in E.fromstring(z.read(target)).findall('m:sheetData/m:row',ns):
    cells={}
    for c in row.findall('m:c',ns):
     typ=c.get('t');value=''
     if typ=='inlineStr':value=''.join(c.find('m:is',ns).itertext())
     else:
      v=c.find('m:v',ns);value='' if v is None else v.text or ''
      if typ=='s':value=shared[int(value)]
      elif typ not in ['str','b','e'] and value:
       try:value=float(value);value=int(value) if value.is_integer() else value
       except ValueError:pass
     cells[re.sub(r'\d','',c.attrib['r'])]=value
    rows.append(cells)
   if not rows:continue
   header=rows[0];ids=[c for c,h in header.items() if h=='안정 ID']
   if not ids:continue
   result[s.attrib['name']]={str(row[ids[0]]):{h:row.get(c,'') for c,h in header.items() if h in FIELDS} for row in rows[1:] if row.get(ids[0])}
 return result
def stable(d,kind='doc'):
 if d.get('stable_id'):return str(d['stable_id'])
 prefix='|'.join(text(d.get(k)) for k in ['project','po','source'])
 if kind=='doc':return prefix
 # Referencing documents grow during translation; they are not an issue's identity.
 prefix='|'.join([text(d.get('project')),text(d.get('po')),kind])
 identity=d.get('msgid') or d.get('term') or d.get('issue') or d.get('source_file') or json.dumps(d,sort_keys=True,ensure_ascii=False)
 # Context prevents distinct term exceptions from collapsing.
 if kind=='term':identity=text(identity)+'|'+text(d.get('context'))+'|'+text(d.get('chosen'))
 return prefix+'|'+hashlib.sha256(str(identity).encode()).hexdigest()[:16]
def human(saved,sheetname,key):
 existing=saved.get(sheetname,{})
 v=existing.get(key,{})
 if not v and sheetname!='문서별 검토':
  # Migrate v1 IDs and preserve reviews when the source-document list expands.
  prefix='|'.join(key.split('|')[:2])+'|';suffix='|'+key.rsplit('|',1)[-1]
  matches=[value for old,value in existing.items() if old.startswith(prefix) and old.endswith(suffix)]
  if len(matches)==1:v=matches[0]
 return [v.get('검토 상태') or '미검토']+[v.get(f,'') for f in FIELDS[1:]]
def ratio(total,translated,expression):
 if total is None or translated is None:return '집계 중'
 return formula(expression,translated/total if total else 0,5)
def make_sheets(data,saved,generated):
 docs=sorted(data.get('documents',[]),key=lambda d:(int(d.get('priority') or 0),d.get('project',''),d.get('po',''),d.get('source','')))
 ids=[stable(d) for d in docs]
 if len(ids)!=len(set(ids)):raise ValueError('문서 안정 ID 중복')
 docrows=[]
 for n,d in enumerate(docs,2):
  total,trans=d.get('total'),d.get('translated')
  if total is not None and trans is not None and not 0<=trans<=total:raise ValueError('잘못된 번역 수')
  priority=int(d.get('priority') or 0)
  scope_label='P0 · 기존 번역' if priority==0 else f'P{priority} · 추가 번역'
  docrows.append([stable(d),scope_label,d.get('project',''),d.get('po',''),d.get('source',''),d.get('summary',''),ratio(total,trans,f'IFERROR(M{n}/L{n},0)'),*human(saved,'문서별 검토',stable(d)),total,trans,d.get('output',''),d.get('review_log',''),text(d.get('source_issues',False)),text(d.get('term_exceptions','')),text(d.get('review_requested',False))])
 headers=['안정 ID','작업 구분 / 우선순위','프로젝트','PO 파일','원본 문서','내용 한줄 요약','번역률',*FIELDS,'문서 항목 수','번역 항목 수','번역 PO 서버 경로','검토 로그 서버 경로','원문 의심 사항','용어 예외 정보','검토 요청 기록']
 specs=[('문서별 검토',sheet(headers,docrows,[12,25,19,24,40,48,12,14,16,16,60,12,12,70,65,35,60,18],edit=(8,9,10,11),status=8,percent=(7,),hidden=True,freeze_cols=5))]
 sumrows=[];end=max(2,len(docs)+1)
 for n,c in enumerate(data.get('catalogs',[]),2):
  project,po=c.get('project',''),c.get('po','');matching=[r for r in docrows if r[2]==project and r[3]==po];counts=collections.Counter(r[7] for r in matching)
  total,trans=c.get('total'),c.get('translated');base=f"'문서별 검토'!$C$2:$C${end},A{n},'문서별 검토'!$D$2:$D${end},B{n}"
  fs=[formula(f'COUNTIFS({base},\'문서별 검토\'!$H$2:$H${end},"{state}")',counts[state]) for state in STATES]
  sumrows.append([project,po,total,trans,ratio(total,trans,f'IFERROR(D{n}/C{n},0)'),len(matching),*fs,c.get('output',''),c.get('scope_total'),c.get('scope_translated'),('통과' if c.get('validation_passed') else '실패') if c.get('validation_current') else '현재 파일 검증 대기'])
 specs.insert(0,('요약',sheet(['프로젝트','PO 파일','PO 고유 항목 수','번역 고유 항목 수','전체 PO 번역률','문서 수',*STATES,'번역 PO 서버 경로','이번 범위 고유 항목 수','이번 범위 번역 수','현재 PO 검증'],sumrows,[22,27,18,20,18,12,12,12,12,12,12,78,23,23,24],percent=(5,),height=42,freeze_cols=2)))
 issues=[]
 for d in data.get('source_issues',[]):
  key=stable(d,'issue');issues.append([key,*[d.get(k,'') for k in ['project','po','source','msgid','issue','reason','suggestion']],*human(saved,'원문 이슈',key),d.get('source_file','')])
 specs.append(('원문 이슈',sheet(['안정 ID','프로젝트','PO 파일','원본 문서','원문 항목','의심 사항','처리 근거','현재 번역',*FIELDS,'근거 파일'],issues,[12,22,25,55,75,65,65,55,14,16,16,60,70],edit=(9,10,11,12),status=9,hidden=True,height=88)))
 terms=[]
 for d in data.get('term_exceptions',[]):
  key=stable(d,'term');terms.append([key,*[d.get(k,'') for k in ['project','po','term','official','chosen','context','reason','source_file']],*human(saved,'용어 예외',key)])
 specs.append(('용어 예외',sheet(['안정 ID','프로젝트','PO 파일','원어','우선 용어집 표기','적용 번역','적용 문맥','예외 근거','프로젝트 용어 기록',*FIELDS],terms,[12,22,25,25,30,30,60,70,70,14,16,16,60],edit=(10,11,12,13),status=10,hidden=True,height=75)))
 guide=[['목적','문서 번역 상태와 사람의 검토 상태를 별도로 관리합니다. 번역률 100%는 승인 완료를 의미하지 않습니다.'],['기준 시각 (한국 표준시)',generated],['원본 데이터 시각',data.get('generated_at','')],['리뷰 입력','문서별 검토의 노란색 검토 상태·검토자·검토일·검토 메모 열에 입력합니다. 원문 이슈와 용어 예외의 검토 상태는 별도로 관리합니다.'],['검토 상태','미검토 → 검토중 → 승인 또는 수정요청으로 기록합니다. 검토를 미루면 보류를 선택합니다. 승인은 검토자가 명시적으로 선택합니다.'],['검토일','YYYY-MM-DD 또는 Excel 날짜로 입력합니다. 시각 기준은 한국 표준시(KST)입니다.'],['작업 구분 / 우선순위','P0 · 기존 번역은 이전에 번역한 선정 범위입니다. P1~P8 · 추가 번역은 추가 SDK 번역 우선순위입니다. 문서별 검토 시트에서 이 열을 필터링하면 기존 번역만 따로 검토할 수 있습니다.'],['포함 문서',f"기존 번역 {sum(int(d.get('priority') or 0)==0 for d in docs)}개와 추가 번역 {sum(int(d.get('priority') or 0)>0 for d in docs)}개를 포함한 전체 {len(docs)}개 문서를 각각 한 행으로 관리합니다."],['항목 수 중복 주의','같은 PO의 문장을 여러 원본 문서가 공유할 수 있습니다. 문서별 항목 수를 합하면 중복됩니다. 실제 고유 항목 수는 요약의 PO 고유 항목 수를 사용합니다.'],['검토 요청 기록','번역 에이전트가 해당 문서의 검토를 요청한 로그가 있는지 표시합니다. 사람의 승인과 별개입니다.'],['집계 중','문서별 POT 매핑이 완료되지 않은 항목 수는 공란, 번역률은 집계 중으로 표시합니다. 미확인 상태를 0%로 처리하지 않습니다.'],['경로 의미','절대 경로는 waffle-ostk-i18n 서버 기준입니다. 이 파일은 번역 PO를 수정하지 않습니다.'],['용어 적용','공식 GitHub OpenStack 한국어 glossary.po → 확인 가능한 weblate.printf.kr 용어 → 프로젝트별 신규 용어 순서입니다. 문맥별 예외는 근거와 함께 기록합니다.'],['요약 집계','검토 상태별 문서 수는 COUNTIFS 수식이며 Excel에서 재계산합니다. 번역 수는 생성 시점 스냅샷입니다. PO 변경만으로 Excel 값이 자동 갱신되지는 않습니다.'],['갱신과 입력 보존','생성기는 기존 XLSX의 안정 ID로 검토 상태·검토자·검토일·검토 메모를 보존합니다. 숨겨진 안정 ID 열을 변경하지 않습니다.'],['파일 백업','갱신 전 기존 출력은 같은 폴더의 .backups에 시각별 보관합니다. 다른 검토본을 반영하려면 생성기의 --existing 옵션으로 지정합니다.'],['공동 편집','별도 복사본을 여러 사람이 수정하면 하나의 검토본으로 취합한 후 갱신합니다. 생성기는 복사본 간 충돌을 자동 해결하지 않습니다.'],['외부 서비스','Weblate·GitHub·Gerrit 업로드 없이 서버에 저장한 번역을 검토합니다. 이 파일의 승인 상태는 외부 서비스 승인을 수행하지 않습니다.']]
 guide += [['작업 참고',text(n)] for n in data.get('notes',[])]
 specs.append(('사용 안내',sheet(['항목','안내'],guide,[27,135],height=48)))
 return specs,{'documents':len(docrows),'catalogs':len(sumrows),'source_issues':len(issues),'term_exceptions':len(terms),'preserved_reviews':sum(k in saved.get('문서별 검토',{}) for k in ids)}
def write_package(path,specs):
 wb=E.Element('{'+N+'}workbook');sub(sub(wb,'bookViews'),'workbookView',{'activeTab':'0'});sheets=sub(wb,'sheets')
 rels=E.Element('Relationships',{'xmlns':P});types=E.Element('Types',{'xmlns':'http://schemas.openxmlformats.org/package/2006/content-types'})
 for ext,typ in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml')]:E.SubElement(types,'Default',{'Extension':ext,'ContentType':typ})
 overrides={'/xl/workbook.xml':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml','/xl/styles.xml':'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml','/docProps/core.xml':'application/vnd.openxmlformats-package.core-properties+xml','/docProps/app.xml':'application/vnd.openxmlformats-officedocument.extended-properties+xml'}
 for n,(name,_) in enumerate(specs,1):
  sub(sheets,'sheet',{'name':name,'sheetId':str(n),'{'+R+'}id':f'rId{n}'})
  E.SubElement(rels,'Relationship',{'Id':f'rId{n}','Type':R+'/worksheet','Target':f'worksheets/sheet{n}.xml'})
  overrides[f'/xl/worksheets/sheet{n}.xml']='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'
 sub(wb,'calcPr',{'calcId':'191029','fullCalcOnLoad':'1','forceFullCalc':'1'})
 E.SubElement(rels,'Relationship',{'Id':f'rId{len(specs)+1}','Type':R+'/styles','Target':'styles.xml'})
 for name,typ in overrides.items():E.SubElement(types,'Override',{'PartName':name,'ContentType':typ})
 rootrels=E.Element('Relationships',{'xmlns':P})
 for i,typ,target in [('rId1',R+'/officeDocument','xl/workbook.xml'),('rId2',P+'/metadata/core-properties','docProps/core.xml'),('rId3',R+'/extended-properties','docProps/app.xml')]:E.SubElement(rootrels,'Relationship',{'Id':i,'Type':typ,'Target':target})
 core=E.Element('{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}coreProperties',{'xmlns:dcterms':'http://purl.org/dc/terms/'})
 E.SubElement(core,'{http://purl.org/dc/elements/1.1/}title').text='OpenStack 한국어 번역 검토 체크리스트'
 E.SubElement(core,'{http://purl.org/dc/elements/1.1/}creator').text='OpenStack 번역 작업'
 E.SubElement(core,'{http://purl.org/dc/terms/}created',{'{http://www.w3.org/2001/XMLSchema-instance}type':'dcterms:W3CDTF'}).text=dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
 app=E.Element('Properties',{'xmlns':'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'});E.SubElement(app,'Application').text='Translation review checklist generator'
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for name,content in [('[Content_Types].xml',xml(types)),('_rels/.rels',xml(rootrels)),('xl/workbook.xml',xml(wb)),('xl/_rels/workbook.xml.rels',xml(rels)),('xl/styles.xml',styles()),('docProps/core.xml',xml(core)),('docProps/app.xml',xml(app))]:z.writestr(name,content)
  for n,(_,content) in enumerate(specs,1):z.writestr(f'xl/worksheets/sheet{n}.xml',content)
def validate_package(path):
 with zipfile.ZipFile(path) as z:
  if z.testzip():raise ValueError('ZIP 무결성 오류')
  names=set(z.namelist())
  for name in names:
   if name.endswith(('.xml','.rels')):E.fromstring(z.read(name))
  for name in names:
   if not name.endswith('.rels'):continue
   base='' if name=='_rels/.rels' else posixpath.dirname(posixpath.dirname(name))
   for rel in E.fromstring(z.read(name)):
    if rel.get('TargetMode')=='External':raise ValueError('외부 관계')
    target=rel.attrib['Target'];target=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(base,target))
    if target not in names:raise ValueError('누락된 OOXML 관계 '+target)
  for name in names:
   if not name.startswith('xl/worksheets/'):continue
   root=E.fromstring(z.read(name));ns={'m':N};addresses=[c.attrib['r'] for c in root.findall('m:sheetData/m:row/m:c',ns)]
   if len(addresses)!=len(set(addresses)):raise ValueError('중복 셀')
   if root.find('m:autoFilter',ns) is None or root.find('m:sheetViews/m:sheetView/m:pane',ns) is None:raise ValueError('필터/고정 헤더 누락')
   for f in root.findall('.//m:f',ns):
    if f.text.startswith('=') or '[' in f.text:raise ValueError('잘못된 수식')
 return {'zip_integrity':True,'xml_parsed':True,'relationships_resolved':True,'filters_and_freeze_panes':True}
def build(input_path,output_path,existing=None):
 out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);data=json.loads(Path(input_path).read_text());saved=read_existing(existing or out)
 generated=dt.datetime.now(KST).isoformat(timespec='seconds');specs,report=make_sheets(data,saved,generated)
 fd,tmp=tempfile.mkstemp(prefix='.translation-review-',suffix='.xlsx',dir=out.parent);os.close(fd);backup=None
 try:
  write_package(tmp,specs);report.update(validate_package(tmp))
  if out.exists():
   folder=out.parent/'.backups';folder.mkdir(exist_ok=True);backup=folder/(out.stem+'.'+dt.datetime.now(KST).strftime('%Y%m%dT%H%M%S%f')+out.suffix);shutil.copy2(out,backup)
  os.replace(tmp,out)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 report.update({'output':str(out.resolve()),'generated_at':generated,'backup':str(backup) if backup else None,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
 out.with_suffix('.validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('output');p.add_argument('--existing');a=p.parse_args();print(json.dumps(build(a.input,a.output,a.existing),ensure_ascii=False,indent=2))
