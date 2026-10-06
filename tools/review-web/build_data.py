"""Export a read-only, paired view from the existing PO/document mappings."""
from pathlib import Path
from collections import defaultdict
from io import BytesIO
from datetime import datetime, timezone
import hashlib,json,shutil,os
from babel.messages.pofile import read_po
BASE=Path('/opt/po-review/work')
RUN=BASE/'translation-support/20261001-expansion'
ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'public'
def write_json(path,data):
    raw=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    temp=path.with_suffix('.tmp');temp.write_text(raw);temp.replace(path)
def main():
    PUBLIC.mkdir(exist_ok=True);(PUBLIC/'data').mkdir(exist_ok=True)
    review=json.loads((RUN/'translation-review-data.json').read_text())
    docs=[];catalogs={};unique=set()
    for cat in review['catalogs']:
        project=cat['project'];name=Path(cat['po']).stem;repo=BASE/project
        raw=Path(cat['output']).read_bytes();po=read_po(BytesIO(raw))
        pot_path=repo/('releasenotes/source' if name=='releasenotes' else 'doc/source')/'locale'/(name+'.pot')
        messages=list(read_po(BytesIO(pot_path.read_bytes())))
        scope=repo/'local-translations/support'/(name+'-scope')
        mp=scope/('full-user-document-map.json' if name=='doc-user' else 'document-map.json')
        mapping={d['source']:d['entry_indices'] for d in json.loads(mp.read_text())['documents']} if mp.exists() else {}
        direct=defaultdict(set)
        for i,m in enumerate(messages):
            if not m.id:continue
            for location,line in m.locations:
                if location.endswith('.rst') and 'source/' in location:
                    prefix='releasenotes/source/' if name=='releasenotes' else 'doc/source/'
                    direct[prefix+location.split('source/',1)[1]].add(i)
        catalogs[(project,cat['po'])]=(po,messages,mapping,direct,hashlib.sha256(raw).hexdigest())
    for meta in review['documents']:
        project=meta['project'];name=meta['po'];source=meta['source']
        po,messages,mapping,direct,digest=catalogs[(project,name)]
        ids=mapping.get(source,sorted(direct[source]))
        assert len(ids)==meta['total'],meta['stable_id']
        entries=[]
        for i in ids:
            m=messages[i];translated=po.get(m.id,context=m.context)
            assert translated is not None and translated.string, (name,i)
            unique.add((project,name,i))
            entry={'index':i,'source':m.id,'translation':translated.string,'context':m.context,'locations':m.locations,'fuzzy':'fuzzy' in translated.flags}
            entries.append(entry)
        key=hashlib.sha256(meta['stable_id'].encode()).hexdigest()[:20]
        issues=[x for x in review['source_issues'] if x['project']==project and x['po']==name and source in x.get('source','').splitlines()]
        entry_by_source={str(e['source']):e for e in entries}
        for issue in issues:
            e=entry_by_source.get(str(issue.get('msgid')))
            if e is not None:e.setdefault('issues',[]).append({'issue':issue.get('issue',''),'reason':issue.get('reason','')})
        write_json(PUBLIC/'data'/(key+'.json'),{**meta,'id':key,'sha256':digest,'entries':entries})
        docs.append({**meta,'id':key})
    assert len(docs)==417 and len(unique)==12575
    shutil.copy2(RUN/'translation-review-checklist.xlsx',PUBLIC/'translation-review-checklist.xlsx')
    manifest={'generated_at':datetime.now(timezone.utc).isoformat(),'documents':docs,'total_entries':len(unique),'catalogs':len(catalogs),'notes':['원문과 번역문의 RST 표기를 그대로 표시합니다.','검토 기록은 Excel에서 관리합니다.']}
    write_json(PUBLIC/'data/index.json',manifest)
    print(json.dumps({'documents':len(docs),'unique_entries':len(unique),'public':str(PUBLIC)}))
if __name__=='__main__':main()
