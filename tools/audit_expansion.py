"""Record source/translation preservation and refresh project terminology indexes."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import hashlib
import json
from babel.messages.pofile import read_po

BASE=Path('/opt/po-review/work')
RUN=BASE/'translation-support/20261001-expansion'

def read(path):
    with path.open('rb') as stream:
        return read_po(stream)

def main():
    baseline=json.loads((RUN/'input-baseline.json').read_text())
    report={'updated_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            'immutable_sources':[], 'preserved_translations':[], 'projects':[]}
    for item in baseline['immutable_sources']:
        current=hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
        report['immutable_sources'].append({'path':item['path'],'unchanged':current==item['sha256']})
    for old in sorted((RUN/'before-expansion').rglob('*.po')):
        project=old.parent.name
        current=BASE/project/'local-translations/ko'/old.name
        before=read(old);after=read(current)
        changed=[];count=0
        for message in before:
            if not message.id or not message.string:
                continue
            count+=1
            target=after.get(message.id,context=message.context)
            if target is None or target.string!=message.string:
                changed.append(message.id)
        report['preserved_translations'].append({'project':project,'po':old.name,'existing_count':count,
            'changed_count':len(changed),'changed_sources':changed})
    for project in ['openstacksdk','skyline-apiserver']:
        folder=BASE/project/'local-translations/ko'
        index={'project':project,'scope':'project-only','catalog_term_files':[],
               'terms':[],'contextual_exceptions':[]}
        for path in sorted(folder.glob('*.terms.json')):
            data=json.loads(path.read_text());index['catalog_term_files'].append(str(path))
            terms=data.get('terms',data.get('project_terms',[]))
            if isinstance(terms,dict):
                terms=[{'source_term':key,'translation':value} for key,value in terms.items()]
            for term in terms:
                source=term.get('source_term',term.get('source',term.get('term')))
                index['terms'].append({**term,'source_term':source,'catalog_term_file':path.name})
            for exception in data.get('contextual_exceptions',data.get('exceptions',[])):
                index['contextual_exceptions'].append({**exception,'catalog_term_file':path.name})
        groups=defaultdict(set)
        for term in index['terms']:
            groups[term['source_term'].casefold()].add(term['translation'])
        conflicts={key:sorted(values) for key,values in groups.items() if len(values)>1}
        report['projects'].append({'project':project,'unique_project_terms':len(groups),
            'contextual_exceptions':len(index['contextual_exceptions']),'term_conflicts':conflicts})
        (folder/'project-terminology.json').write_text(json.dumps(index,ensure_ascii=False,indent=2))
    report['preservation_passed']=all(item['unchanged'] for item in report['immutable_sources']) and not any(item['changed_count'] for item in report['preserved_translations'])
    report['term_consistency_passed']=not any(item['term_conflicts'] for item in report['projects'])
    (RUN/'expansion-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'preservation_passed':report['preservation_passed'],
        'term_consistency_passed':report['term_consistency_passed'],'projects':report['projects']},ensure_ascii=False))

if __name__=='__main__':
    main()
