# Project Graph Schema

## 0. 문서 목적

이 문서는 `Observed Graph`와 `Curated Graph`의 데이터 스펙을 정의한다.

핵심 목적은 다음과 같다.

1. 코드 스캔 결과를 표준 구조로 저장한다.
2. 사용자가 수정 가능한 운영 그래프를 분리한다.
3. planner와 executor가 동일한 계약을 사용하게 만든다.

---

## 1. Graph 타입 구분

## 1.1 Observed Graph

자동 분석 결과다.

특징:

1. detector 기반
2. confidence 포함
3. 오류 가능성 있음
4. 사용자 검토 전 상태

## 1.2 Curated Graph

운영 확정 결과다.

특징:

1. 사람이 수정/승인함
2. orchestration의 기준 입력
3. profile과 dependency가 확정됨

---

## 2. 최상위 구조

```json
{
  "schema_version": "1.0",
  "graph_type": "observed",
  "workspace": {},
  "repositories": [],
  "services": [],
  "dependencies": [],
  "profiles": [],
  "policies": [],
  "metadata": {}
}
```

필수 필드:

1. `schema_version`
2. `graph_type`
3. `workspace`
4. `repositories`
5. `services`
6. `dependencies`
7. `profiles`
8. `policies`
9. `metadata`

---

## 3. workspace 객체

```json
{
  "id": "ws_ora",
  "name": "ora-platform",
  "slug": "ora-platform",
  "default_branch": "main",
  "vcs_provider": "github"
}
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | workspace id |
| name | string | 이름 |
| slug | string | slug |
| default_branch | string | 기본 브랜치 |
| vcs_provider | string | github/gitlab/local |

---

## 4. repositories 배열

```json
[
  {
    "id": "repo_oraserver",
    "provider": "github",
    "org": "mike",
    "name": "OraServer",
    "default_branch": "main",
    "repo_kind": "single-service",
    "local_path": "/workspace/Ora/OraServer"
  }
]
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | repo id |
| provider | string | github/gitlab/local |
| org | string | org or owner |
| name | string | repo name |
| default_branch | string | 기본 브랜치 |
| repo_kind | string | monorepo/single-service/docs/infra |
| local_path | string | 로컬 경로 |

---

## 5. services 배열

서비스는 graph의 핵심 단위다.

```json
[
  {
    "id": "svc_oraserver_api",
    "repository_id": "repo_oraserver",
    "name": "OraServer",
    "slug": "oraserver-api",
    "root_path": "/",
    "service_type": "backend",
    "runtime": "jvm",
    "framework": "spring-boot",
    "language": "java",
    "ports": [8080],
    "capabilities": [
      "http-api",
      "telephony-core",
      "unit-test"
    ],
    "detectors": [
      {
        "name": "gradle_detector",
        "evidence": ["build.gradle", "src/main/java"],
        "confidence": 0.98
      }
    ],
    "execution_profile_id": "profile_spring_gradle",
    "status": "active"
  }
]
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | service id |
| repository_id | string | repo 참조 |
| name | string | 표시 이름 |
| slug | string | 식별자 |
| root_path | string | 레포 내 경로 |
| service_type | string | frontend/backend/android/ai/docs/infra/worker |
| runtime | string | node/python/jvm/android/docker/static |
| framework | string | react/fastapi/spring 등 |
| language | string | 주언어 |
| ports | number[] | 노출 포트 |
| capabilities | string[] | 능력 목록 |
| detectors | Detector[] | 근거 |
| execution_profile_id | string | profile 참조 |
| status | string | active/disabled |

### Detector 객체

```json
{
  "name": "package_json_detector",
  "evidence": ["package.json", "playwright.config.ts"],
  "confidence": 0.94
}
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| name | string | detector 이름 |
| evidence | string[] | 근거 파일/패턴 |
| confidence | number | 0~1 |

---

## 6. dependencies 배열

```json
[
  {
    "id": "dep_web_to_api",
    "from_service_id": "svc_web",
    "to_service_id": "svc_api",
    "dependency_type": "http",
    "required_for": ["run", "e2e"],
    "confidence": 0.92,
    "evidence": [
      "NEXT_PUBLIC_API_URL",
      "frontend/src/lib/api.ts"
    ]
  }
]
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | dependency id |
| from_service_id | string | 소비자 |
| to_service_id | string | 제공자 |
| dependency_type | string | http/queue/db/build/runtime/test-fixture |
| required_for | string[] | run/test/deploy/research |
| confidence | number | 0~1 |
| evidence | string[] | 근거 |

---

## 7. profiles 배열

```json
[
  {
    "id": "profile_node_playwright",
    "profile_name": "node-playwright",
    "runtime_family": "node",
    "executor_type": "remote_worker",
    "worker_kind": "node-qa",
    "commands": {
      "install": "npm ci",
      "build": "npm run build",
      "start": "npm run dev",
      "test_e2e": "npx playwright test"
    },
    "healthcheck": {
      "type": "http",
      "url": "http://localhost:3000"
    },
    "timeouts": {
      "startup_seconds": 120,
      "test_seconds": 900
    },
    "env_schema": [
      {"name": "BASE_URL", "required": true}
    ]
  }
]
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | profile id |
| profile_name | string | profile 이름 |
| runtime_family | string | node/python/jvm/android |
| executor_type | string | in_process/subprocess/remote_worker |
| worker_kind | string | python-research/node-qa/android-qa |
| commands | object | install/build/start/test command |
| healthcheck | object | healthcheck 정의 |
| timeouts | object | timeout 정의 |
| env_schema | object[] | env 요구사항 |

---

## 8. policies 배열

```json
[
  {
    "id": "policy_web_qa",
    "scope": "service",
    "service_id": "svc_web",
    "policy_type": "qa",
    "rules": {
      "allow_e2e": true,
      "allow_visual_regression": false,
      "require_backend_ready": true
    }
  }
]
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | string | policy id |
| scope | string | workspace/service/profile |
| service_id | string | 대상 서비스 |
| policy_type | string | qa/research/ops/deploy |
| rules | object | 정책 rule |

---

## 9. metadata 객체

```json
{
  "graph_type": "observed",
  "analyzer_version": "v1.0.0",
  "generated_at": "2026-03-07T10:00:00Z",
  "source_revision": "abcdef1234",
  "summary": {
    "repo_count": 5,
    "service_count": 8,
    "dependency_count": 11
  }
}
```

필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| graph_type | string | observed/curated |
| analyzer_version | string | 분석기 버전 |
| generated_at | string | ISO timestamp |
| source_revision | string | git SHA 등 |
| summary | object | 요약 |

---

## 10. Observed Graph 제약

Observed Graph에는 아래 필드가 반드시 포함되어야 한다.

1. 모든 service에 `detectors`
2. 모든 dependency에 `confidence`
3. 모든 capability가 `detected` 성격임을 구분할 수 있는 근거
4. 미확정 항목은 `status` 또는 `confidence`로 표시

Observed Graph에는 허용되지만 Curated Graph에는 최소화해야 하는 것:

1. 낮은 confidence 결과
2. 중복 service 후보
3. 확정되지 않은 profile

---

## 11. Curated Graph 제약

Curated Graph는 아래 조건을 만족해야 한다.

1. 실행 대상 service가 고유하게 확정됨
2. dependency가 실행 기준으로 충분히 정제됨
3. service별 `execution_profile_id`가 확정됨
4. orchestration에 필요한 policy가 채워짐

Curated Graph에서는 다음이 금지된다.

1. 동일 `slug`의 중복 service
2. 없는 profile을 참조하는 service
3. 없는 service를 참조하는 dependency
4. 실행 불가능한 profile

---

## 12. Validation 규칙

필수 validation:

1. 모든 `repository_id`는 repositories에 존재해야 함
2. 모든 `execution_profile_id`는 profiles에 존재해야 함
3. 모든 dependency의 `from_service_id`, `to_service_id`는 services에 존재해야 함
4. 모든 `service.id`는 고유해야 함
5. 모든 `profile.id`는 고유해야 함
6. `graph_type`은 `observed` 또는 `curated`
7. `schema_version`은 semver 형식

Curated 전용 validation:

1. `execution_profile_id` 누락 금지
2. `status=active` service는 실행 가능 profile 필수
3. `dependency_type=runtime`이면 readiness 전략 필요

---

## 13. Planner 입력으로의 변환

Planner는 graph 전체를 그대로 소비할 수도 있지만, 실제로는 아래 형태로 정규화해서 쓰는 것이 좋다.

```json
{
  "workspace": {"id": "ws_ora"},
  "services": [
    {
      "id": "svc_web",
      "type": "frontend",
      "runtime": "node",
      "capabilities": ["web-ui", "e2e"],
      "profile": "profile_node_playwright"
    }
  ],
  "dependencies": [
    {
      "from": "svc_web",
      "to": "svc_api",
      "kind": "http",
      "required_for": ["e2e"]
    }
  ]
}
```

---

## 14. Executor 입력으로의 변환

Executor는 graph 전체가 아니라 service + profile 중심 payload를 받는다.

예시:

```json
{
  "service_id": "svc_web",
  "profile": {
    "runtime_family": "node",
    "worker_kind": "node-qa",
    "commands": {
      "install": "npm ci",
      "test_e2e": "npx playwright test"
    }
  },
  "dependencies_ready": [
    {
      "service_id": "svc_api",
      "healthcheck_url": "http://localhost:8080/health"
    }
  ]
}
```

---

## 15. Sample Curated Graph

```json
{
  "schema_version": "1.0",
  "graph_type": "curated",
  "workspace": {
    "id": "ws_ora",
    "name": "ora-platform",
    "slug": "ora-platform",
    "default_branch": "main",
    "vcs_provider": "github"
  },
  "repositories": [
    {
      "id": "repo_web",
      "provider": "github",
      "org": "mike",
      "name": "OraWebAppFrontend",
      "default_branch": "main",
      "repo_kind": "single-service",
      "local_path": "/workspace/Ora/OraWebAppFrontend"
    }
  ],
  "services": [
    {
      "id": "svc_web",
      "repository_id": "repo_web",
      "name": "B2C Web",
      "slug": "b2c-web",
      "root_path": "/",
      "service_type": "frontend",
      "runtime": "node",
      "framework": "react",
      "language": "typescript",
      "ports": [3000],
      "capabilities": ["web-ui", "e2e"],
      "detectors": [],
      "execution_profile_id": "profile_node_playwright",
      "status": "active"
    }
  ],
  "dependencies": [],
  "profiles": [
    {
      "id": "profile_node_playwright",
      "profile_name": "node-playwright",
      "runtime_family": "node",
      "executor_type": "remote_worker",
      "worker_kind": "node-qa",
      "commands": {
        "install": "npm ci",
        "build": "npm run build",
        "start": "npm run dev",
        "test_e2e": "npx playwright test"
      },
      "healthcheck": {
        "type": "http",
        "url": "http://localhost:3000"
      },
      "timeouts": {
        "startup_seconds": 120,
        "test_seconds": 900
      },
      "env_schema": []
    }
  ],
  "policies": [],
  "metadata": {
    "graph_type": "curated",
    "analyzer_version": "v1.0.0",
    "generated_at": "2026-03-07T10:00:00Z",
    "source_revision": "abcdef1234",
    "summary": {
      "repo_count": 1,
      "service_count": 1,
      "dependency_count": 0
    }
  }
}
```

---

## 16. 다음 단계

이 문서 다음으로 실제 코드 변경 순서를 정리한 문서는 다음이다.

1. [REFACTOR_SEQUENCE.md](/Users/mike/workspace/side_project/Ora/ora-automation/REFACTOR_SEQUENCE.md)
