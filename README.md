# ora-automation

`ora-automation`는 `Ora` 메인 서버와 분리된 다중 에이전트형 자동화 루트입니다.
현재는 R&D 자동화(기존 엔진)와 E2E 자동화를 같은 루트에서 관리합니다.

## 자동화 항목 구조

- `automations/research`: R&D 전략 생성·토론·검증 결과 축적
- `automations/e2e`: 서비스별 E2E 오케스트레이션 가이드(`automations/e2e/services`)
- `automations/qa`: 향후 QA 자동화(리포트/회귀/게이트) 전개 예정

각 세부 규칙은 각 하위 폴더의 README를 참고하세요.
현재 오케스트레이션은 `CEO / Planner / Developer` 3명의 협업 에이전트로 설계되어 있습니다.

- **CEO**: 시장성/수주성/사업성 중심의 점수 산정
- **Planner**: 사용자 체감 품질·업무 확장성·로드맵 적합성 중심의 점수 산정
- **Developer**: 기존 파이프라인 재사용성, 구현 난이도, 단기 실현성 중심의 점수 산정

## 구성

- `src/ora_rd_orchestrator/engine.py`
  - 워크스페이스 스캔, 토픽 점수 산정, 에이전트 랭킹 산출, 보고서 생성
- `src/ora_rd_orchestrator/cli.py`
  - CLI 진입점
- `scripts/run_collaboration_cycle.sh`
  - 반복 실행 러너(과거 보고서 자동 반영 + 실전 웹 검증 자동 실행)
- `scripts/verify_sources.py`
  - 실전 웹 검증기(연구 출처 URL 상태 실시간 확인, arXiv API 교차 검증, 재시도)
- `Makefile`
  - 원클릭 실행 타깃
- `research_reports/`
  - 과거 보고서 템플릿/소스(샘플 V9) 보관

## 실전 웹 검증기 (research_sources.json 자동 갱신기)

`research_sources.json`은 주제별 출처 URL 목록입니다.
`verify_sources.py`는 아래를 수행합니다.

- URL 접근 확인(HTTP 상태)
- 응답 지연/최종 URL/타이틀 수집
- arXiv 링크는 API로 논문 존재 여부 교차 검증(`verified_by_arxiv_api`)
- DOI/학술 링크는 `Crossref API`, `OpenAlex API` fallback 검증으로 오탐/사라진 논문을 걸러냄
- 미검증 항목 재시도(`--rounds`, `--retry-delay`)
- 검사 결과를 `sources[].status`에 반영하고 `validation` 요약 저장

### 검색 전략(왜 API 기반인지)

- **arXiv/Crossref/OpenAlex API 우선**: 메타데이터 신뢰도 높은 구조화 응답을 받으므로, 제목/저자/발행 연도 검증 정확도가 높고 크롤러보다 일관적입니다.
- **공식 페이지는 웹 fallback**: 최신 공지/문서/벤더 페이지는 API에 안 잡히는 경우가 많아 검색 포털·공식 홈페이지 링크를 보조로 수집합니다.
- **무료 API 정책 대응**: 과도 사용 시 rate-limit/429가 발생할 수 있어, `VERIFY_SCOPE` 반복, 타임아웃 조절, provider toggle로 비용·오탐·지연을 제어합니다.
- **크롤러와의 차이**: 크롤러는 최신 UI/텍스트를 볼 수 있지만 반응형 DOM/차단 정책에 민감해 재현성이 낮습니다. 현재 구조는 API(근거형) + 웹 접근성 확인(보조)로 운영 안정성을 우선합니다.

관련 환경변수(오케스트레이션/엔진 공통)

- `ORA_RD_RESEARCH_ARXIV_SEARCH`, `ORA_RD_RESEARCH_CROSSREF_SEARCH`, `ORA_RD_RESEARCH_OPENALEX_SEARCH` (`1`/`0`)
- `ORA_RD_RESEARCH_SEARCH_TIMEOUT`, `ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS`, `ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS`, `ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS`
- `ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT`, `ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT`
- 하위호환: `ORA_RD_ARXIV_SEARCH_ENABLED`, `ORA_RD_ARXIV_SEARCH_MAX_RESULTS`, `ORA_RD_ARXIV_SEARCH_TIMEOUT`

## 원클릭 실행 방법 (Makefile)

```bash
cd /Users/mike/workspace/side_project/Ora/ora-automation

# 1) 최초 셋업
make setup

# 2) 1회 분석 실행
make run

# 2-b) 한 개 전략만 뽑는 실행(요청한 형식에 맞춤)
make run-single FOCUS=OraB2bAndroid VERSION_TAG=V10

# 2-b) 포커스 라벨 지정 실행 (예: OraB2bAndroid)
make run-focus FOCUS=OraB2bAndroid VERSION_TAG=V10

# 3) 반복 러너(기본값 V10_자동회차)
make run-cycle

# 3-b) 반복 러너 + 에이전트 토론 라운드 강화(예: 4회)
make run-cycle DEBATE_ROUNDS=4

# 4) 반복 러너 + 다중 검증 라운드(기본 3회)
make run-cycle-verify VERIFY_ROUNDS=3

# 4-b) 딥 모드 반복 러너(확장 스캔 + 강한 검증)
make run-cycle-deep RUN_CYCLES=3 VERIFY_ROUNDS=5

# 4-c) 논문 소스 신뢰도 강화(공식 API만 사용)
make run-cycle DEBATE_ROUNDS=3 ORA_RD_RESEARCH_CROSSREF_SEARCH=1 ORA_RD_RESEARCH_OPENALEX_SEARCH=1 ORA_RD_RESEARCH_SEARCH_TIMEOUT=10

# 4-d) 특정 provider만 끌 때 (예: arXiv만)
make run-cycle ORA_RD_RESEARCH_ARXIV_SEARCH=1 ORA_RD_RESEARCH_CROSSREF_SEARCH=0 ORA_RD_RESEARCH_OPENALEX_SEARCH=0

# 5) 반복 횟수 증가해 더 끈질기게 수행
make run-loop RUN_CYCLES=3 VERIFY_ROUNDS=4
make run-loop RUN_CYCLES=3 VERIFY_ROUNDS=4 DEBATE_ROUNDS=4

# 6) 존재 소스 파일만 검증
make verify-sources VERIFY_SOURCE_FILES="/Users/mike/workspace/side_project/Ora/ora-automation/research_reports/V9_대화흐름혁신_업무자동화_신뢰성강화/research_sources.json"
```

### 실행 파라미터 오버라이드

```bash
make run TOP=5 WORKSPACE=/Users/mike/workspace/side_project/Ora OUTPUT_DIR=/tmp/ora-research-output
make run-focus FOCUS=OraB2bAndroid VERSION_TAG=V10 KEEP_LAST_RUNS=4 RUN_NAME=V10_안드로이드
make run-single FOCUS=OraB2bAndroid VERSION_TAG=V10
```

## 수동 실행

```bash
python3 src/ora_rd_orchestrator/cli.py \
  --workspace /Users/mike/workspace/side_project/Ora \
  --output-dir /Users/mike/workspace/side_project/Ora/ora-automation/research_reports/runs/manual \
  --output-name rd_research_report_$(date +%Y%m%d_%H%M%S) \
  --top 6 \
  --debate-rounds 3

# 한 개 전략 단위 리포트
python3 src/ora_rd_orchestrator/cli.py \
  --workspace /Users/mike/workspace/side_project/Ora \
  --output-dir /Users/mike/workspace/side_project/Ora/ora-automation/research_reports/runs/manual \
  --output-name rd_research_report_$(date +%Y%m%d_%H%M%S) \
  --single-strategy \
  --focus OraB2bAndroid \
  --version-tag V10
```

러너 실행 예:

```bash
cd /Users/mike/workspace/side_project/Ora/ora-automation
bash scripts/run_collaboration_cycle.sh
```

## 출력

- Markdown: `rd_research_report_YYYYmmdd_HHMMSS.md`
- JSON: `rd_research_report_YYYYmmdd_HHMMSS.json`
- Sources: `research_sources.json` (실행 폴더 내 생성, 검증 상태 자동 갱신)
- 반복 결과(기본): `research_reports/V10_자동회차/<timestamp>/`
- 포커스 실행: `research_reports/V10_자동회차/<focus-slug>/<timestamp>/`

JSON 핵심 필드
- `ranked`: 통합 점수 순위
- `agent_scores`: CEO/Planner/Developer 별 점수
- `agent_scores_initial`: 토론 전 초기 점수
- `agent_rankings`: 에이전트별 TopN ID
- `debate_rounds_requested`: CLI 요청 토론 라운드 수
- `debate_rounds_executed`: 수렴 기반 실제 실행 라운드 수
- `consensus`: 가중 합의 후보
- `research_queries`: 상위 주제의 웹 검증 검색 키워드
- `discussion`: 라운드별 에이전트 토론 로그(지원/반대 메시지, confidence/evidence, 안정성 지표)

## 분리형 사용 이유

기존 Ora 소스 코드 변경 없이 별도 폴더에서 실행/버전관리할 수 있도록 구성했습니다.
`src`와 `scripts`가 자체적으로 동작하므로, 연구 자동화 파이프라인만 독립 운영할 수 있습니다.


## E2E(Cypress) 자동화

`ora-automation`에서 바로 E2E 실행 타깃을 붙였습니다.

```bash
cd /Users/mike/workspace/side_project/Ora/ora-automation

# 1) Cypress 설치 (기본 npm)
make e2e-install E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend

# 1-b) Playwright 설치 (기본 npm)
make e2e-playwright-install E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend

# 2) 설치 후 Cypress GUI 실행
make e2e-open E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend

# 3) 설치 후 Headless 실행
make e2e-run E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend

# 3-b) 설치 후 Playwright Headless 실행
make e2e-run E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend E2E_TOOL=playwright

# 4) Playwright UI 실행
make e2e-open E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend E2E_TOOL=playwright

# 옵션: pnpm 사용 시
make e2e-open E2E_PM=pnpm E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend
```

- `E2E_PROJECT_DIR`: Cypress를 실행할 프론트엔드 폴더
- `E2E_PM`: 패키지 매니저(`npm` / `pnpm` / `yarn`, 기본 `npm`)
- `E2E_BASE_URL`: e2e 실행 시 baseUrl override
- `E2E_TOOL`: `cypress` 또는 `playwright` (기본: `cypress`)
- `E2E_CONFIG_FILE`: config 파일 경로 지정 시 사용
- `E2E_SPEC_FILE`: 특정 spec 파일만 실행할 때 사용

### 서비스별 E2E 분리 실행

`automations/e2e/services/` 기준에서 서비스 단위로 실행하도록 정리했습니다.

```bash
cd /Users/mike/workspace/side_project/Ora/ora-automation

# B2B: OraB2bServer (Gradle e2e)
make e2e-service SERVICE=b2b

# B2C: OraWebAppFrontend (기본: npm test)
make e2e-service SERVICE=b2c

# B2C를 Playwright로 실행
make e2e-service SERVICE=b2c E2E_TOOL=playwright

# Android: OraB2bAndroid (Gradle :app:test)
make e2e-service SERVICE=android

# AI: OraAiServer LLM/TTS (pytest)
make e2e-service SERVICE=ai

# 통신: OraServer (Gradle test)
make e2e-service SERVICE=telecom

# 5개 기본 슬롯을 한 번에
make e2e-service-all

# AI 테스트 인수 조정
make e2e-service SERVICE=ai E2E_PYTEST_ARGS="tests/test_scenario_edge.py -q"

# B2C를 Cypress로 강제 실행
make e2e-service SERVICE=b2c E2E_FORCE_CYPRESS=1 E2E_SERVICE_MODE=open
```

### 지원 서비스 목록

```bash
make e2e-service-list
```

- `b2b` - OraB2bServer
- `android` - OraB2bAndroid (`:app:test`)
- `b2c` - OraWebAppFrontend
- `ai` - OraAiServer (LLM/TTS pytest)
- `telecom` - OraServer (통신)
