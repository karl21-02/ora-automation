# GitHub Workflow / 깃허브 활용 규칙

ora-automation 프로젝트의 브랜치 전략, 커밋 컨벤션, PR 규칙, 이슈 관리, 코드 리뷰, CI/CD 가이드입니다.

---

## Table of Contents / 목차

- [Branch Strategy / 브랜치 전략](#branch-strategy--브랜치-전략)
- [Commit Convention / 커밋 컨벤션](#commit-convention--커밋-컨벤션)
- [Pull Request / PR 규칙](#pull-request--pr-규칙)
- [Issue Management / 이슈 관리](#issue-management--이슈-관리)
- [Code Review / 코드 리뷰](#code-review--코드-리뷰)
- [CI/CD Pipeline](#cicd-pipeline)
- [Release / 릴리스](#release--릴리스)
- [Security / 보안](#security--보안)

---

## Branch Strategy / 브랜치 전략

GitHub Flow 기반의 단순한 브랜치 전략을 사용합니다.

```
main (production-ready)
  │
  ├── feat/chatbot-streaming      ← 기능 개발
  ├── fix/gemini-token-expiry     ← 버그 수정
  ├── docs/api-reference          ← 문서 작업
  ├── refactor/pipeline-modular   ← 리팩토링
  ├── chore/update-dependencies   ← 기타 작업
  └── hotfix/critical-db-fix      ← 긴급 수정
```

### Branch Naming / 브랜치 네이밍

```
<type>/<short-description>
```

| Type | 용도 | 예시 |
|---|---|---|
| `feat` | 새 기능 | `feat/realtime-run-status` |
| `fix` | 버그 수정 | `fix/sse-stream-disconnect` |
| `docs` | 문서 | `docs/api-reference-update` |
| `refactor` | 리팩토링 | `refactor/research-parallel` |
| `chore` | 설정, 의존성 등 | `chore/upgrade-react-19` |
| `hotfix` | 긴급 수정 | `hotfix/db-migration-crash` |
| `test` | 테스트 추가/수정 | `test/pipeline-unit-tests` |

### Rules / 규칙

1. **`main`은 항상 배포 가능 상태**를 유지한다
2. 모든 변경은 **브랜치 → PR → 리뷰 → merge** 흐름을 따른다
3. 브랜치는 `main`에서 생성하고, `main`으로 merge한다
4. merge 후 브랜치는 삭제한다
5. `main`에 직접 push하지 않는다 (hotfix 제외, 사유 기록 필수)

### Branch Lifecycle / 브랜치 생명주기

```bash
# 1) 브랜치 생성
git checkout main
git pull origin main
git checkout -b feat/my-feature

# 2) 작업 & 커밋
git add <files>
git commit -m "feat: add streaming run status"

# 3) 푸시 & PR 생성
git push -u origin feat/my-feature
# GitHub에서 PR 생성

# 4) 리뷰 & merge 후 로컬 정리
git checkout main
git pull origin main
git branch -d feat/my-feature
```

---

## Commit Convention / 커밋 컨벤션

[Conventional Commits](https://www.conventionalcommits.org/) 규격을 따릅니다.

### Format / 형식

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type / 타입

| Type | 설명 | 예시 |
|---|---|---|
| `feat` | 새 기능 추가 | `feat(chat): add SSE streaming endpoint` |
| `fix` | 버그 수정 | `fix(worker): handle stale lock recovery` |
| `docs` | 문서 변경 | `docs: update API reference` |
| `refactor` | 코드 리팩토링 (기능 변화 없음) | `refactor(pipeline): extract scoring module` |
| `test` | 테스트 추가/수정 | `test(api): add orchestration CRUD tests` |
| `chore` | 빌드, 설정, 의존성 변경 | `chore: upgrade FastAPI to 0.115` |
| `style` | 포맷팅, 세미콜론 등 (기능 변화 없음) | `style: fix lint warnings` |
| `perf` | 성능 개선 | `perf(research): parallelize API calls` |
| `ci` | CI/CD 설정 변경 | `ci: add GitHub Actions workflow` |
| `revert` | 이전 커밋 되돌리기 | `revert: feat(chat): add SSE streaming` |

### Scope / 스코프 (선택)

| Scope | 대상 |
|---|---|
| `api` | `src/ora_automation_api/` |
| `pipeline` | `src/ora_rd_orchestrator/pipeline.py` 및 관련 모듈 |
| `chat` | 챗봇 관련 (chat_router, chatbot) |
| `worker` | 워커 프로세스 |
| `frontend` | `frontend/` |
| `agent` | `src/ora_rd_orchestrator/agent/` |
| `research` | 리서치 모듈 (research, web_sources) |
| `docker` | Dockerfile, docker-compose |
| `make` | Makefile |
| `deps` | 의존성 (pyproject.toml, package.json) |

### Subject / 제목 규칙

- 영어로 작성 (한국어 본문은 허용)
- 소문자로 시작
- 명령형 현재 시제 (`add`, `fix`, `update` — `added`, `fixed` 아님)
- 마침표 없음
- 50자 이내

### Body / 본문 (선택)

- 제목과 한 줄 띄워서 작성
- "무엇을"이 아닌 **"왜"** 변경했는지 설명
- 한국어 허용
- 72자 줄바꿈 권장

### Footer / 꼬리말 (선택)

- `BREAKING CHANGE:` — 호환성 깨지는 변경
- `Closes #123` — 이슈 자동 닫기
- `Refs #456` — 관련 이슈 참조
- `Co-Authored-By:` — 공동 작업자 (선택, AI 도구 사용 시 생략)

### Examples / 예시

```
feat(chat): add SSE streaming for chat endpoint

Gemini Vertex AI의 streamGenerateContent API를 활용하여
토큰 단위 실시간 스트리밍을 구현했습니다.

- chat_router.py에 /chat/stream 엔드포인트 추가
- 리전 폴백 지원 (asia-northeast3 → us-central1)
- 스트리밍 완료 후 plan/choices 추출

Closes #12
```

```
fix(worker): prevent zombie lock on worker crash

워커 프로세스가 비정상 종료 시 locked_by가 해제되지 않아
다른 워커가 해당 run을 처리하지 못하는 문제를 수정했습니다.

heartbeat_at 기준 stale_timeout(120초) 초과 시 자동 해제하도록 변경.

Refs #34
```

```
chore(docker): add __pycache__ to .gitignore
```

---

## Pull Request / PR 규칙

### PR Template / PR 템플릿

PR 생성 시 아래 형식을 따릅니다.

```markdown
## Summary / 요약
<!-- 1~3줄로 변경사항을 설명하세요 -->

## Changes / 변경 내역
- [ ] 변경 1
- [ ] 변경 2

## Related Issues / 관련 이슈
- Closes #<number>
- Refs #<number>

## Test Plan / 테스트 계획
- [ ] 로컬에서 `make api-up` 후 정상 동작 확인
- [ ] 관련 엔드포인트 curl 테스트
- [ ] 프론트엔드 빌드 확인 (`cd frontend && npx vite build`)

## Screenshots / 스크린샷
<!-- UI 변경 시 첨부 -->

## Checklist
- [ ] 커밋 메시지가 컨벤션을 따르는가
- [ ] 불필요한 파일이 포함되지 않았는가 (__pycache__, .env, credentials)
- [ ] 문서 업데이트가 필요한 경우 반영했는가
- [ ] 기존 기능에 영향을 주지 않는가
```

### PR Rules / PR 규칙

1. **제목**: 커밋 컨벤션과 동일한 형식 (`feat(scope): description`)
2. **크기**: 가능한 작게 유지 (300줄 이하 권장, 최대 500줄)
3. **하나의 PR = 하나의 목적**: 기능과 리팩토링을 같은 PR에 섞지 않는다
4. **Draft PR**: 작업 중이면 Draft로 열어 진행 상황을 공유한다
5. **Self-review**: PR 생성 전 본인이 먼저 diff를 확인한다

### Merge Strategy / 머지 전략

| 상황 | 전략 |
|---|---|
| 일반 기능/수정 | **Squash and merge** (커밋 이력 정리) |
| 대규모 변경 (각 커밋이 의미 있는 경우) | **Merge commit** |
| 충돌 없는 단순 변경 | **Rebase and merge** |

기본은 **Squash and merge**를 사용합니다.

### Labels / 라벨

| Label | 색상 | 설명 |
|---|---|---|
| `feat` | `#0E8A16` | 새 기능 |
| `fix` | `#D93F0B` | 버그 수정 |
| `docs` | `#0075CA` | 문서 |
| `refactor` | `#E4E669` | 리팩토링 |
| `chore` | `#CCCCCC` | 설정/유지보수 |
| `priority: high` | `#B60205` | 긴급 |
| `priority: low` | `#C2E0C6` | 낮은 우선순위 |
| `wip` | `#FBCA04` | 작업 중 |
| `needs-review` | `#5319E7` | 리뷰 필요 |
| `frontend` | `#1D76DB` | 프론트엔드 |
| `backend` | `#006B75` | 백엔드 |
| `infra` | `#D4C5F9` | 인프라/Docker |

---

## Issue Management / 이슈 관리

### Issue Template / 이슈 템플릿

#### Bug Report / 버그 리포트

```markdown
## Bug Description / 버그 설명
<!-- 어떤 문제가 발생하는지 설명 -->

## Steps to Reproduce / 재현 방법
1. ...
2. ...

## Expected Behavior / 기대 동작
<!-- 정상이라면 어떻게 되어야 하는지 -->

## Actual Behavior / 실제 동작
<!-- 실제로 어떻게 되는지 -->

## Environment / 환경
- OS:
- Docker version:
- Python version:
- Node version:

## Logs / 로그
```
(관련 로그 붙여넣기)
```
```

#### Feature Request / 기능 요청

```markdown
## Feature Description / 기능 설명
<!-- 원하는 기능을 설명 -->

## Motivation / 배경
<!-- 왜 이 기능이 필요한지 -->

## Proposed Solution / 제안하는 방법
<!-- 어떻게 구현할 수 있을지 -->

## Alternatives / 대안
<!-- 다른 방법이 있다면 -->
```

### Issue Labels / 이슈 라벨

이슈 생성 시 적절한 라벨을 붙입니다 (PR 라벨과 동일한 세트 사용).

### Milestones / 마일스톤

버전별 마일스톤으로 이슈를 그룹핑합니다.

| Milestone | 설명 |
|---|---|
| `v0.3.0` | 실시간 실행 상태 추적 + 리서치 병렬화 |
| `v0.4.0` | ReAct 에이전트 모드 완성 |
| `v1.0.0` | 프로덕션 릴리스 |

---

## Code Review / 코드 리뷰

### Review Checklist / 리뷰 체크리스트

리뷰어는 아래 항목을 확인합니다.

#### Correctness / 정확성
- [ ] 로직이 의도대로 동작하는가
- [ ] 엣지 케이스를 처리했는가
- [ ] 에러 핸들링이 적절한가

#### Security / 보안
- [ ] 시크릿이 코드에 하드코딩되지 않았는가
- [ ] SQL injection, XSS 등 취약점이 없는가
- [ ] 입력 검증이 적절한가

#### Performance / 성능
- [ ] 불필요한 DB 쿼리가 없는가
- [ ] N+1 문제가 없는가
- [ ] 타임아웃/리소스 해제가 적절한가

#### Style / 스타일
- [ ] 프로젝트 컨벤션을 따르는가
- [ ] 네이밍이 명확한가
- [ ] 불필요한 주석이 없는가

### Review Response / 리뷰 응답

| 표현 | 의미 |
|---|---|
| `LGTM` | 승인 (Looks Good To Me) |
| `nit:` | 사소한 제안 (반영 안 해도 됨) |
| `suggestion:` | 개선 제안 (반영 권장) |
| `question:` | 이해를 위한 질문 |
| `blocker:` | 반드시 수정 필요 (merge 차단) |

---

## CI/CD Pipeline

### GitHub Actions (계획)

현재 CI/CD는 미설정 상태이며, 아래 단계로 점진 도입합니다.

#### Phase 1: Basic Checks / 기본 체크

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - uses: actions/setup-node@v4
        with: { node-version: '18' }
      - run: pip install -e .
      - run: python -c "from ora_automation_api.main import app; print('API OK')"
      - run: cd frontend && npm ci && npx tsc --noEmit
      - run: cd frontend && npx vite build
```

#### Phase 2: Docker Build / 도커 빌드

```yaml
  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build
```

#### Phase 3: Integration Tests / 통합 테스트

```yaml
  integration:
    runs-on: ubuntu-latest
    services:
      postgres: { image: 'postgres:16-alpine', ... }
      rabbitmq: { image: 'rabbitmq:3.13', ... }
    steps:
      - run: pytest tests/ -v
```

### Required Checks / 필수 체크 (도입 시)

PR merge 전 통과해야 하는 체크:

| Check | 설명 |
|---|---|
| `lint-and-type-check` | Python import + TypeScript 타입 체크 |
| `frontend-build` | 프론트엔드 빌드 성공 |
| `docker-build` | Docker 이미지 빌드 성공 |

---

## Release / 릴리스

### Versioning / 버전 관리

[Semantic Versioning](https://semver.org/)을 따릅니다.

```
v<MAJOR>.<MINOR>.<PATCH>

MAJOR: 호환성 깨지는 변경
MINOR: 하위 호환되는 기능 추가
PATCH: 하위 호환되는 버그 수정
```

현재 버전: `v0.2.0` (pyproject.toml 및 FastAPI app version 기준)

### Release Process / 릴리스 프로세스

```bash
# 1) 버전 업데이트
# pyproject.toml → version = "0.3.0"
# src/ora_automation_api/main.py → version="0.3.0"

# 2) 커밋 & 태그
git commit -am "chore: bump version to v0.3.0"
git tag -a v0.3.0 -m "v0.3.0: 실시간 실행 상태 추적, 리서치 병렬화"
git push origin main --tags

# 3) GitHub Release 생성
gh release create v0.3.0 --title "v0.3.0" --notes "..."
```

### Changelog / 변경 이력

릴리스 노트에는 아래 형식으로 변경사항을 기록합니다.

```markdown
## v0.3.0 (2025-03-10)

### Features / 기능
- 실행 상태 실시간 SSE 추적 (#15)
- 리서치 API 병렬 호출 (#18)

### Fixes / 수정
- Gemini 토큰 mid-execution 갱신 (#20)

### Docs / 문서
- GitHub 워크플로우 문서 추가 (#22)
```

---

## Security / 보안

### Sensitive Files / 민감한 파일

아래 파일은 **절대 커밋하지 않습니다**.

| 파일 | 설명 |
|---|---|
| `google-service-account.json` | GCP 서비스 계정 키 |
| `.env` | 환경변수 파일 |
| `*.pem`, `*.key` | 인증서/키 파일 |
| `credentials.json` | 기타 인증 정보 |

`.gitignore`에 반드시 포함되어야 합니다.

### Secret Management / 시크릿 관리

- 로컬 개발: 환경변수 또는 `.env` 파일 (git에 미포함)
- Docker: `docker-compose.yml`의 `environment` 섹션
- CI/CD: GitHub Secrets (`Settings → Secrets and variables → Actions`)
- 프로덕션: GCP Secret Manager 또는 환경변수 주입

### Pre-commit Checks / 커밋 전 확인

커밋 전 아래를 확인합니다.

```bash
# 시크릿 파일이 스테이징되지 않았는지 확인
git diff --cached --name-only | grep -E '\.(env|pem|key|json)$'

# __pycache__가 포함되지 않았는지 확인
git diff --cached --name-only | grep __pycache__
```
