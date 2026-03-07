# Refactor Sequence

## 0. 문서 목적

이 문서는 현재 `ora-automation` 코드베이스를 어떤 순서로 바꿔야 안전하게 일반화 아키텍처로 이동할 수 있는지 정의한다.

핵심 목표는 다음과 같다.

1. 기존 기능을 최대한 유지한다.
2. 토스형 조직 커스터마이징 구조를 깨지 않는다.
3. R&D, QA, Ops 실행 구조를 점진적으로 일반화한다.

---

## 1. 현재 코드 기준 핵심 문제

현재 코드에서 먼저 해결해야 하는 문제는 다음과 같다.

1. target 문자열 중심 실행
2. Ora 전용 서비스 인식 흔적
3. project graph 부재
4. organization과 execution 대상의 연결 부족
5. worker/runtime 분리 부족

즉, 지금의 문제는 "설계가 없음"이 아니라 "설계를 담을 중간 계층이 비어 있음"이다.

---

## 2. 리팩토링 원칙

1. 새 계층을 추가한 뒤 기존 경로를 점진적으로 교체한다.
2. organization 관련 구조는 먼저 건드리지 않는다.
3. graph와 executor가 준비되기 전에는 target 분기를 제거하지 않는다.
4. 연구 파이프라인은 우선 보존하고, QA 계열부터 분리한다.

---

## 3. 단계별 리팩토링 순서

## Step 1. 설정/상수 계층 정리

### 목표

Ora 전용 고정 enum과 실행 상수를 한 곳에 모은다.

### 작업

1. 고정 service name 탐지
2. 허용 target 목록 정리
3. `intent`, `scope`, `service_type`, `runtime_family` 상수 정의
4. 기존 문자열 분기를 adapter 계층 뒤로 이동

### 결과

1. 현재 동작은 유지
2. 다음 단계에서 graph 기반 분기 추가 가능

---

## Step 2. DB 모델 확장

### 목표

새 프로젝트 계층 모델을 먼저 추가한다.

### 작업

1. `tenants`
2. `workspaces`
3. `repositories`
4. `services`
5. `service_capabilities`
6. `service_dependencies`
7. `execution_profiles`
8. `observed_project_graphs`
9. `curated_project_graphs`
10. `secret_sets`
11. `orchestrations` 확장
12. `orchestration_runs`, `run_steps` 확장

### 주의

1. organization 관련 테이블은 유지
2. 기존 chat/org 기능은 깨지면 안 됨

---

## Step 3. Graph domain 모델 추가

### 목표

DB와 별개로 Python 내부 graph model을 먼저 만든다.

### 작업

1. `graph_models.py`
2. `graph_validation.py`
3. `graph_serialization.py`
4. `graph_loader.py`

### 결과

1. 코드 분석기와 planner가 공통 graph contract를 사용할 수 있음

---

## Step 4. Workspace analyzer 분리

### 목표

현재 흩어진 코드/문서 분석 로직을 graph 생성기로 올린다.

### 작업

1. repository scanner 추가
2. detector registry 추가
3. service detector
4. dependency detector
5. profile detector
6. observed graph writer

### 결과

1. `analyze_workspace()`류 함수가 단순 요약이 아니라 graph 생성기로 바뀜

---

## Step 5. Curation 계층 추가

### 목표

자동 분석 결과를 그대로 실행하지 않도록 막는다.

### 작업

1. observed graph 조회 API
2. curated graph 저장 API
3. graph diff 생성
4. graph patch 적용

### 결과

1. 실행은 curated graph 기준으로만 가능해짐

---

## Step 6. Planner 입력 통합

### 목표

organization과 graph가 planner 입력에서 함께 쓰이도록 만든다.

### 작업

1. planner input schema 확정
2. organization serializer 정리
3. curated graph loader 연결
4. user request -> intent parser 정리
5. deliberation 입력에 organization + graph 주입

### 결과

1. "누가 판단하느냐"와 "무엇을 실행하느냐"가 동시에 planner에 들어감

---

## Step 7. Execution Plan 객체 도입

### 목표

문자열 target 실행 대신 구조화된 실행 계획을 사용한다.

### 작업

1. `ExecutionPlan`
2. `ExecutionStep`
3. readiness checks
4. dependency ordering
5. rollback metadata

### 예시

```json
{
  "intent": "qa",
  "steps": [
    {"kind": "start_service", "service_id": "svc_api"},
    {"kind": "healthcheck", "service_id": "svc_api"},
    {"kind": "e2e_test", "service_id": "svc_web"}
  ]
}
```

### 결과

1. target 문자열에 의존하지 않음

---

## Step 8. Executor Registry 도입

### 목표

실행 단위를 executor로 표준화한다.

### 작업

1. `ExecutorRegistry`
2. `ResearchExecutor`
3. `VerifySourcesExecutor`
4. `PlaywrightExecutor`
5. `CypressExecutor`
6. `PytestExecutor`
7. `GradleExecutor`
8. `AndroidInstrumentationExecutor`

### 연결 규칙

1. service_type
2. runtime_family
3. capabilities
4. execution_profile

### 결과

1. `qa-program`이 research pipeline으로 잘못 들어가는 문제 제거

---

## Step 9. Service layer 분기 교체

### 목표

현재 서비스 레이어의 단일 실행 경로를 executor 기반으로 교체한다.

### 작업

1. `create_run()`에 graph/org 연결
2. `execute_run()`에서 planner output 로드
3. `_run_pipeline()`의 역할 축소
4. `_run_external_target()` 대신 executor dispatch

### 주의

1. 기존 research 경로는 우선 보존
2. QA/E2E부터 새 executor로 이동

---

## Step 10. Worker 분리

### 목표

런타임에 맞는 worker로 실행을 분리한다.

### 작업

1. `python-research-worker`
2. `node-qa-worker`
3. `android-qa-worker`
4. routing key 설계
5. run step status callback

### 결과

1. Python worker가 Playwright/Cypress/Gradle까지 다 끌고 가지 않음

---

## Step 11. Frontend onboarding/capture 추가

### 목표

일반 사용자가 프로젝트를 등록하고 수정할 수 있게 한다.

### 작업

1. GitHub 연결 UI
2. repo 선택 UI
3. observed graph 검토 UI
4. curated graph 편집 UI
5. execution profile 수정 UI
6. org binding UI

---

## Step 12. 운영 안정화

### 목표

실패 복구와 산출물 관리 정책을 고정한다.

### 작업

1. run retry policy
2. step timeout
3. artifact retention
4. telemetry
5. failure labeling
6. partial success 처리

---

## 4. 실제 파일 기준 권장 작업 순서

현재 코드베이스 기준으로 먼저 손대야 할 범주는 다음 순서가 맞다.

## 4.1 1차 변경 대상

1. API 모델/스키마 계층
2. service layer
3. planner/deliberation input
4. storage layer

## 4.2 2차 변경 대상

1. analyzer 계층
2. worker routing
3. frontend graph UI

## 4.3 3차 변경 대상

1. node worker
2. android worker
3. telemetry/ops

---

## 5. 호환성 전략

리팩토링 도중 기존 기능을 유지하려면 아래 전략이 필요하다.

### 5.1 Dual path 유지

당분간은 두 경로를 같이 둔다.

1. legacy target path
2. graph/executor path

단, 새로운 기능은 전부 graph/executor path에만 추가한다.

### 5.2 Feature flag

필요한 플래그:

1. `ENABLE_PROJECT_GRAPH`
2. `ENABLE_CURATED_GRAPH_REQUIRED`
3. `ENABLE_EXECUTOR_REGISTRY`
4. `ENABLE_NODE_QA_WORKER`
5. `ENABLE_ANDROID_WORKER`

### 5.3 Backward compatibility

기존 run 생성 요청이 target 문자열만 줘도, 내부에서 planner input으로 변환하는 adapter를 둔다.

---

## 6. 테스트 순서

## 6.1 먼저 작성할 테스트

1. graph validation test
2. observed -> curated transition test
3. planner input composition test
4. executor selection test

## 6.2 그다음 테스트

1. service dependency ordering test
2. worker routing test
3. onboarding API test

## 6.3 마지막 통합 테스트

1. research orchestration integration
2. web QA orchestration integration
3. android orchestration integration

---

## 7. 절대 하면 안 되는 리팩토링

1. organization 구조를 먼저 갈아엎는 것
2. graph 없이 target 문자열만 늘리는 것
3. 모든 걸 shell script로 우회하는 것
4. Python worker 하나에 Playwright/Cypress/Gradle을 계속 몰아넣는 것
5. curated 단계 없이 observed 결과를 바로 운영에 쓰는 것

---

## 8. 최소 구현 단위

실제 코드 작업은 아래 최소 단위로 쪼개는 것이 맞다.

### PR 1

1. DB schema 추가
2. graph models 추가

### PR 2

1. observed graph 생성기
2. observed graph 저장 API

### PR 3

1. curated graph API
2. planner input 통합

### PR 4

1. execution plan 객체
2. executor registry

### PR 5

1. QA executor 분리
2. research executor 정리

### PR 6

1. node worker 추가
2. queue routing

### PR 7

1. onboarding UI
2. graph review UI

### PR 8

1. integration tests
2. telemetry
3. 운영 문서

---

## 9. 최종 판단 기준

리팩토링이 끝났다고 말하려면 아래 조건을 충족해야 한다.

1. 조직 커스터마이징 기능이 그대로 동작한다.
2. 새 workspace onboarding 시 observed graph가 생성된다.
3. curated graph 없이는 실행이 제한된다.
4. planner가 organization + graph를 같이 입력으로 받는다.
5. executor가 service/profile 기준으로 선택된다.
6. research와 QA가 다른 worker/runtime에서 실행된다.

---

## 10. 바로 다음 코드 작업

이 문서 다음의 실제 코드 작업 시작점은 다음 순서다.

1. DB 모델 추가
2. graph model 추가
3. observed graph writer 추가
4. service layer의 executor registry 뼈대 추가
