from pathlib import Path
import sys,json,time,hashlib,traceback
from sphinx_render import metadata,groupof,appfor,render,ROOT
from lxml import html

def main():
 group=sys.argv[1];out=ROOT/'rendered';out.mkdir(exist_ok=True);results=[];failures=[];start=time.monotonic()
 with (ROOT/'build'/group/'preflight.log').open('w') as log:
  app=appfor(group,log)
  for d in metadata()['documents']:
   if groupof(d)!=group:continue
   try:
    for language in ['en','ko']:
     body=render(d,language,existing=app);tree=html.fromstring(body)
     if d['total'] and not tree.xpath('//*[@data-entry]'):raise AssertionError('No editable nodes')
     digest=hashlib.sha256(Path(d['output']).read_bytes()).hexdigest() if language=='ko' else 'source-v1'
     path=out/(d['id']+'-'+language+'-'+digest+'.html');path.write_text(body)
    results.append(d['id'])
   except Exception as e:failures.append({'id':d['id'],'source':d['source'],'error':str(e),'traceback':traceback.format_exc()})
   if (len(results)+len(failures))%50==0:print(json.dumps({'group':group,'checked':len(results)+len(failures),'failed':len(failures)}),flush=True)
 report={'group':group,'passed':len(results),'failures':failures,'seconds':round(time.monotonic()-start,1)}
 (ROOT/'build'/group/'preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False),flush=True)
 if failures:sys.exit(1)
if __name__=='__main__':main()
