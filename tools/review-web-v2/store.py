"""Validated, conflict-aware PO edits with exact preservation of other entries."""
from pathlib import Path
from io import BytesIO
from datetime import datetime,timezone
import hashlib,json,re,os,tempfile,subprocess,threading,fcntl,uuid,importlib.util
from babel.messages.pofile import read_po
class Conflict(Exception):pass
class Invalid(Exception):pass
class Store:
 def __init__(self,manifest_path,data_dir,private_dir):
  self.manifest=json.loads(Path(manifest_path).read_text());self.docs={d['id']:d for d in self.manifest['documents']};self.data_dir=Path(data_dir);self.private=Path(private_dir);self.private.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.cache={}
 def catalog(self,path):
  p=Path(path);stat=p.stat();key=(stat.st_mtime_ns,stat.st_size)
  with self.lock:
   if path not in self.cache or self.cache[path][0]!=key:
    raw=p.read_bytes();self.cache[path]=(key,raw,list(read_po(BytesIO(raw))),hashlib.sha256(raw).hexdigest())
   return self.cache[path][1:]
 def document(self,id):
  d=self.docs[id];base=json.loads((self.data_dir/(id+'.json')).read_text());raw,messages,digest=self.catalog(d['output'])
  for e in base['entries']:
   m=messages[e['index']]
   if m.id!=e['source'] or m.context!=e.get('context'):raise Conflict('원문 목록이 변경되었습니다. 문서 매핑을 다시 생성해야 합니다.')
   e['translation']=m.string;e['fuzzy']='fuzzy' in m.flags
  base.update(d);base['sha256']=digest
  return base
 def save(self,id,index,previous,translation):
  if not isinstance(translation,str) or not translation.strip() or len(translation)>200000:raise Invalid('비어 있지 않은 번역문을 입력해 주세요.')
  if '\x00' in translation:raise Invalid('허용되지 않는 제어 문자입니다.')
  d=self.docs[id];path=Path(d['output']);lockpath=self.private/(hashlib.sha256(str(path).encode()).hexdigest()+'.lock')
  with self.lock,lockpath.open('a') as guard:
   fcntl.flock(guard,fcntl.LOCK_EX)
   raw,messages,digest=self.catalog(str(path));doc=self.document(id)
   if not any(e['index']==index for e in doc['entries']):raise Invalid('이 문서에 없는 번역 항목입니다.')
   m=messages[index]
   if not isinstance(m.id,str) or not isinstance(m.string,str):raise Invalid('이 항목은 별도 PO 편집기가 필요합니다.')
   if m.string!=previous:raise Conflict('다른 곳에서 이 항목을 수정했습니다. 최신 번역을 불러온 뒤 다시 저장해 주세요.')
   if translation==m.string:return {'sha256':digest,'changed':False}
   validate(m,translation)
   parts=re.split(r'(\n[ \t]*\n)',raw.decode('utf-8'));found=0
   for n,block in enumerate(parts):
    if not re.search(r'^msgid ',block,re.M):continue
    cat=read_po(BytesIO((block+'\n').encode()));target=cat.get(m.id,context=m.context)
    if target is None:continue
    lines=block.splitlines(keepends=True)
    start=next((j for j,line in enumerate(lines) if line.startswith('msgstr ')),None)
    if start is None:raise Invalid('번역 필드 위치를 찾지 못했습니다.')
    end=start+1
    while end<len(lines) and lines[end].startswith('"'):end+=1
    tail='\n' if lines[end-1].endswith('\n') else ''
    lines[start:end]=['msgstr '+json.dumps(translation,ensure_ascii=False)+tail]
    parts[n]=''.join(lines);found+=1
   if found!=1:raise Invalid('번역 항목을 유일하게 찾지 못했습니다.')
   candidate=''.join(parts).encode('utf-8');after=list(read_po(BytesIO(candidate)))
   if len(after)!=len(messages):raise Invalid('PO 항목 수가 변경되었습니다.')
   for j,(before,new) in enumerate(zip(messages,after)):
    if (before.id,before.context,before.locations,before.flags)!=(new.id,new.context,new.locations,new.flags):raise Invalid('PO 원문 또는 메타데이터가 변경되었습니다.')
    if new.string!=(translation if j==index else before.string):raise Invalid('다른 번역 항목이 변경되었습니다.')
   fd,tmp=tempfile.mkstemp(prefix='.'+path.stem+'-review-',suffix='.po',dir=path.parent)
   try:
    with os.fdopen(fd,'wb') as f:f.write(candidate);f.flush();os.fsync(f.fileno())
    check=subprocess.run(['msgfmt','--check','-o','/dev/null',tmp],capture_output=True,text=True,timeout=20)
    if check.returncode:raise Invalid('PO 검증 실패: '+check.stderr[:1500])
    if path.read_bytes()!=raw:raise Conflict('저장 중 PO 파일이 변경되었습니다. 다시 시도해 주세요.')
    when=datetime.now(timezone.utc).isoformat();eventid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    backups=self.private/'backups';backups.mkdir(exist_ok=True)
    backup=backups/(eventid+'-'+path.name);backup.write_bytes(raw)
    newsha=hashlib.sha256(candidate).hexdigest()
    event={'id':eventid,'time':when,'document':id,'source_document':d['source'],'po':str(path),'index':index,'msgid':m.id,'before':m.string,'after':translation,'before_sha256':digest,'after_sha256':newsha,'backup':str(backup)}
    (self.private/(eventid+'.json')).write_text(json.dumps(event,ensure_ascii=False,indent=2))
    os.chmod(tmp,path.stat().st_mode&0o777);os.replace(tmp,path);self.cache.pop(str(path),None)
    return {'sha256':newsha,'changed':True,'saved_at':when,'backup':str(backup)}
   finally:
    if os.path.exists(tmp):os.unlink(tmp)

def validate(message,value):
 spec=importlib.util.spec_from_file_location('catalog_validation','/opt/po-review/work/translation-support/20261001/validate_catalog.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 if re.search(r'^\s*\.\.\s+(raw|include|literalinclude)::',value,re.M):raise Invalid('번역문에 파일 삽입 또는 raw 지시문을 넣을 수 없습니다.')
 old,ow,ol=module.parse(message.string);new,nw,nl=module.parse(value)
 if old!=new:raise Invalid('코드 리터럴이 변경되었습니다. 코드 표기를 유지해 주세요.')
 if module.role_targets(message.id)!=module.role_targets(value):raise Invalid('문서 참조나 API 식별자가 변경되었습니다.')
 if ol!=nl:raise Invalid('링크 주소가 변경되었습니다.')
 if nw-ow:raise Invalid('RST 문법을 확인해 주세요: '+', '.join((nw-ow).keys())[:1200])
