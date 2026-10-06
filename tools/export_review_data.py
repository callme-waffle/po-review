"""Export live PO/document metadata; never change translation catalogs."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import hashlib
import io
import json
from babel.messages.pofile import read_po

BASE = Path('/opt/po-review/work')
RUN = BASE / 'translation-support/20261001-expansion'
TASKS = [('openstacksdk', 'doc', 1), ('openstacksdk', 'doc-install', 0),
         ('openstacksdk', 'doc-user', 5), ('openstacksdk', 'doc-contributor', 6),
         ('openstacksdk', 'releasenotes', 8), ('skyline-apiserver', 'doc-install', 0),
         ('skyline-apiserver', 'doc-configuration', 0)]

def read_catalog(path):
    with path.open('rb') as stream:
        return read_po(stream)

def complete(message):
    if message is None or not message.id or 'fuzzy' in message.flags:
        return False
    value = message.string
    return bool(value) and (all(value) if isinstance(value, (tuple, list)) else True)

def document_names(value):
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str) and item]
    return []

def main():
    data = {'generated_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'server': 'review-host', 'documents': [], 'catalogs': [],
        'source_issues': [], 'term_exceptions': [], 'notes': [
        '번역 완료와 사람이 수행한 리뷰 승인은 별개입니다. 최초 리뷰 상태는 모두 미검토입니다.',
        '문서별 항목에는 공유 msgid가 중복됩니다. 문서 행의 항목 수를 합산하지 마세요. 요약의 PO별 항목 수는 고유 항목 기준입니다.',
        '우선순위 0은 이전 선정 범위이며 추가 번역은 1→2→3→4→5→6→7→8 순서입니다.',
        '조회 시점의 번역 현황입니다. 미확정 문서별 집계는 공란이며 0개라는 뜻이 아닙니다.',
        '신규 용어와 문맥별 예외는 프로젝트별로 관리하며 공식 OpenStack 한국어 용어집을 우선합니다.',
        'Weblate 용어집 일부는 HTTP 429로 미확인입니다. 조사 제한은 기존 translation-policy.json에 기록했습니다.',
        'PO·POT·검토 로그 경로는 review-host 서버의 경로입니다. 플랫폼 업로드는 수행하지 않습니다.',
        '리뷰 상태·검토자·검토일·메모는 재생성 시 stable_id로 기존 Excel에서 보존합니다.']}
    for project, name, priority in TASKS:
        repo = BASE/project
        folder = repo/'local-translations/ko'
        po = folder/f'{name}.po'
        source_root = repo/('releasenotes/source' if name == 'releasenotes' else 'doc/source')
        src = read_catalog(source_root/'locale'/f'{name}.pot')
        po_bytes = po.read_bytes() if po.exists() else None
        dst = read_po(io.BytesIO(po_bytes)) if po_bytes is not None else None
        messages = list(src)
        translated = sum(complete(dst.get(m.id, context=m.context)) for m in messages if m.id) if dst else 0
        report_path = folder/f'{name}.validation.json'
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        digest = hashlib.sha256(po_bytes).hexdigest() if po_bytes is not None else ''
        if report.get('po_sha256') != digest:
            reports = repo/'local-translations/support'/f'{name}-scope'
            for candidate in sorted(reports.glob('validation*.json'), key=lambda p:p.stat().st_mtime, reverse=True):
                snapshot = json.loads(candidate.read_text())
                if snapshot.get('po_sha256') == digest:
                    report = snapshot
                    break
        data['catalogs'].append({'project': project, 'po': name+'.po', 'output': str(po),
            'total': len(src), 'translated': translated, 'scope_total': len(src),
            'scope_translated': translated, 'priority': priority,
            'validation_current': report.get('po_sha256') == digest,
            'validation_passed': report.get('passed') if report.get('po_sha256') == digest else None})
        review_log = folder/f'{name}.review.jsonl'
        reviews = {}
        if review_log.exists():
            for line in review_log.read_text().splitlines():
                event = json.loads(line)
                source = event.get('source', event.get('document', event.get('source_document')))
                reviews[source] = event
        if name == 'doc':
            paths = [repo/'doc/source'/f for f in ['index.rst', 'glossary.rst', 'releasenotes.rst']]
        elif name == 'releasenotes':
            paths = sorted(source_root.glob('*.rst'))
        else:
            paths = sorted((repo/'doc/source'/name.removeprefix('doc-')).rglob('*.rst'))
        scope_dir = repo/'local-translations/support'/f'{name}-scope'
        map_path = scope_dir/('full-user-document-map.json' if name == 'doc-user' else 'document-map.json')
        mapping = {d['source']: d for d in json.loads(map_path.read_text())['documents']} if map_path.exists() else {}
        direct = defaultdict(set)
        for index, message in enumerate(messages):
            if message.id:
                for location, _ in message.locations:
                    if location.endswith('.rst') and 'source/' in location:
                        prefix = 'releasenotes/source/' if name == 'releasenotes' else 'doc/source/'
                        direct[prefix + location.split('source/', 1)[1]].add(index)
        catalog_rows = []
        for path in paths:
            source = str(path.relative_to(repo))
            mapped = mapping.get(source, {})
            event = reviews.get(source, {})
            indices = mapped.get('entry_indices')
            # Autodoc/Reno must use complete mappings instead of title-only source references.
            if indices is None and name not in ['doc-user', 'doc-contributor', 'releasenotes']:
                indices = sorted(direct[source])
            total = len(indices) if indices is not None else None
            done = sum(complete(dst.get(messages[i].id, context=messages[i].context)) for i in indices) if indices is not None and dst else (0 if indices is not None else None)
            summary = event.get('summary', mapped.get('description_ko', mapped.get('summary', '')))
            if not summary and event.get('message'):
                parts = event['message'].split(' | ')
                if len(parts) >= 3:
                    summary = parts[2]
            if not summary:
                summary = path.stem + (' 릴리스 변경 이력' if name == 'releasenotes' else ' 문서')
            row = {'stable_id': f'{project}|{name}.po|{source}', 'project': project, 'po': name+'.po',
                'priority': mapped.get('priority', priority), 'source': source, 'output': str(po),
                'summary': summary, 'total': total, 'translated': done,
                'review_log': str(review_log), 'review_requested': source in reviews,
                'source_issues': 0, 'term_exceptions': 0, 'entry_indices': indices}
            data['documents'].append(row)
            catalog_rows.append(row)
        notes_path = scope_dir/'source-review-notes.json'
        if notes_path.exists():
            payload = json.loads(notes_path.read_text())
            notes = payload if isinstance(payload, list) else payload.get('notes', payload.get('issues', []))
            for note in notes:
                docs = set(document_names(note.get('documents')))
                doc = note.get('source_document', note.get('document'))
                docs.update(document_names(doc))
                docs.update(document_names(note.get('source_documents')))
                idx = note.get('index')
                message = messages[idx] if isinstance(idx, int) and 0 < idx < len(messages) else None
                msgid = message.id if message else note.get('msgid', note.get('source', ''))
                current = dst.get(message.id, context=message.context) if message and dst else None
                translation = current.string if current else note.get('translation', '')
                docs.update(r['source'] for r in catalog_rows if idx is not None and idx in (r['entry_indices'] or []))
                for r in catalog_rows:
                    if r['source'] in docs:
                        r['source_issues'] += 1
                data['source_issues'].append({'project': project, 'po': name+'.po', 'source': '\n'.join(sorted(docs)),
                    'msgid': msgid, 'issue': note.get('issue', ''),
                    'reason': note.get('handling', note.get('resolution', note.get('reason', ''))),
                    'suggestion': translation, 'source_file': str(notes_path)})
        terms_path = folder/f'{name}.terms.json'
        if terms_path.exists():
            terms = json.loads(terms_path.read_text())
            for exception in terms.get('contextual_exceptions', terms.get('exceptions', [])):
                doc = exception.get('document', exception.get('source_document'))
                docs = set(document_names(doc))
                ids = {i for i in exception.get('source_indices', exception.get('messages', [])) if isinstance(i, int)}
                docs.update(document_names(exception.get('documents')))
                docs.update(document_names(exception.get('source_documents')))
                for item in exception.get('sources', []):
                    if isinstance(item, dict):
                        doc = item.get('document', item.get('source_document'))
                        docs.update(document_names(doc))
                        docs.update(document_names(item.get('documents')))
                        docs.update(document_names(item.get('source_documents')))
                        if isinstance(item.get('index'), int):
                            ids.add(item['index'])
                    elif isinstance(item, int):
                        ids.add(item)
                    elif isinstance(item, str) and item.endswith('.rst'):
                        docs.add(item)
                docs.update(r['source'] for r in catalog_rows if ids.intersection(r['entry_indices'] or []))
                for r in catalog_rows:
                    if r['source'] in docs:
                        r['term_exceptions'] += 1
                data['term_exceptions'].append({'project': project, 'po': name+'.po',
                    'term': exception.get('term', exception.get('source', exception.get('source_term', ''))),
                    'official': exception.get('official', exception.get('official_translation', '')),
                    'chosen': exception.get('selected', exception.get('translation', exception.get('chosen_translation', ''))),
                    'context': exception.get('context', ''), 'reason': exception.get('reason', ''),
                    'source': '\n'.join(sorted(docs)), 'source_file': str(terms_path)})
    data['documents'].sort(key=lambda r: (r['priority'], r['project'], r['po'], r['source']))
    for row in data['documents']:
        row.pop('entry_indices')
    output = RUN/'translation-review-data.json'
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps({'output': str(output), 'documents': len(data['documents']), 'catalogs': len(data['catalogs']),
        'source_issues': len(data['source_issues']), 'term_exceptions': len(data['term_exceptions'])}, ensure_ascii=False))

if __name__ == '__main__':
    main()
