# PO Review

Sphinx/RST 문서의 원문과 PO 번역문을 비교하고, 번역 수정·문서 승인·Weblate 반영을 수행하는 리뷰 서비스입니다.

이 저장소의 초기 버전은 기존 단일 공유 작업환경의 로컬 소스 스냅샷입니다. 사용자별 로그인, Ubuntu 컨테이너, 사용자 직접 프로젝트 등록, 선택적 SSH/SFTP 접근은 후속 이슈에서 구현합니다.

## 현재 구성

- `tools/review-web-v2/`: 공유 접속키 로그인, 원문/번역 렌더링, PO 편집·검증, 문서 승인 및 Weblate 반영.
- `tools/review-web/`: 초기 읽기 전용 화면과 데이터 생성 도구.
- `tools/build_review_checklist.py` 및 관련 도구: 리뷰 데이터 추출·체크리스트 생성.
- `tools/review-web-v2/WORKFLOW-OPERATIONS.txt`: 공개용 운영 절차 요약. 내부 배포 정보는 포함하지 않습니다.

## 실행과 검증의 제약

아직 독립 실행 가능한 배포 패키지는 아닙니다. 원래 서버의 절대 경로, 번역 저장소, manifest, 별도 validate_catalog.py, Weblate 설정 등에 의존합니다. 초기 공개 스냅샷은 서비스 로직을 보존하고 배포 주소와 경로를 예시 값으로 치환합니다.

주요 의존성은 Python, Babel, Sphinx, docutils, lxml, requests, 프로젝트별 Sphinx 확장 및 gettext의 msgfmt입니다. 정확한 버전과 재현 가능한 설치 절차는 첫 설계 이슈에서 조사합니다.

실행용 access.json, 번역 산출물, 원격 접근키, 백업, SQLite 이력과 렌더링 캐시는 업로드하지 않습니다. 기존 HTTP/브라우저 시험은 서버 및 로컬 인증 파일을 참조하므로 운영 대상을 향해 무작정 실행하지 마세요.

문법 검사(서비스를 실행하지 않음):

```sh
python3 - <<'PY'
import ast
from pathlib import Path
for path in Path("tools").rglob("*.py"):
    ast.parse(path.read_text(), filename=str(path))
print("Python syntax OK")
PY
```

## 개발 절차

이슈 하나를 전담 관리 세션에서 관리하고, 독립 작업은 하위 구현 세션으로 분리합니다. 브랜치는 `feat/brief`, `refactor/brief`, `docs/brief`, `chore/brief` 등 일반적인 태그를 사용합니다. 구현·검증 후 PR을 작성하여 저장소 소유자의 리뷰를 받으며 자동 병합하지 않습니다.

상세 규칙은 [AGENTS.md](AGENTS.md)를 따릅니다.

## 공개 스냅샷의 배포 설정

공개 저장소 업로드 시 기존 내부 서버 주소와 개인 배포 경로를 localhost 및 예시 경로로 치환했습니다. 실제 배포 설정과 원본은 공개하지 않습니다. 예시 Weblate 주소는 작동하는 서비스가 아니며 실행 전 설정이 필요합니다. 서비스 로직의 재현성과 실행 환경 분리는 첫 설계 이슈에서 검증합니다.
