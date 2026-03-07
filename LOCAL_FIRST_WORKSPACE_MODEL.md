# Local-first Workspace Model

## 0. 문서 목적

이 문서는 `ora-automation`이 오픈소스 로컬 도구로 배포될 때, 사용자의 프로젝트를 어떤 연결 방식으로 이해하고 다뤄야 하는지 정의한다.

핵심 전제는 다음과 같다.

1. 사용자는 자기 컴퓨터에서 직접 실행한다.
2. 사용자는 로컬 폴더를 직접 연결할 수 있다.
3. GitHub 연동은 선택 사항이다.
4. GitHub 메타데이터와 로컬 실행 상태를 함께 활용하는 하이브리드 모드가 중요하다.

---

## 1. Workspace 분류

Local-first 기준에서 workspace는 아래 다섯 타입으로 나눈다.

## 1.1 `local_only`

특징:

1. 로컬 폴더만 연결됨
2. Git 없음
3. GitHub 없음

읽을 수 있는 것:

1. 폴더 구조
2. `.env*`
3. `Makefile`
4. `docker-compose.yml`
5. `package.json`
6. `pyproject.toml`
7. `build.gradle`

## 1.2 `local_git`

특징:

1. 로컬 `.git` 있음
2. GitHub 연동은 없음 또는 미설정

추가로 읽을 수 있는 것:

1. branch
2. recent commits
3. dirty state
4. remote URL 존재 여부

## 1.3 `linked_repo`

특징:

1. GitHub repo 단위 연결
2. org 전체가 아니라 특정 repo만 연결

추가로 읽을 수 있는 것:

1. GitHub Actions
2. repo metadata
3. default branch
4. workflow definitions

## 1.4 `linked_org`

특징:

1. GitHub organization 단위 연결
2. 여러 repo 탐색 가능

추가로 가능한 것:

1. org 내 repo discovery
2. 여러 repo 자동 workspace 구성
3. org 차원의 메타데이터 분석

## 1.5 `hybrid`

특징:

1. 로컬 경로도 있음
2. GitHub repo/org 연결도 있음
3. 가장 현실적인 개발자 모드

읽을 수 있는 것:

1. 로컬 `.env`
2. 로컬 브랜치/dirty state
3. GitHub Actions
4. repo metadata
5. local runtime 상태

---

## 2. 핵심 설계 원칙

## 2.1 연결 방식과 실행 위치를 분리한다

중요한 건 GitHub 연동 여부와 실제 실행 위치가 다를 수 있다는 점이다.

예:

1. GitHub는 연결돼 있지만 실행은 로컬에서 한다.
2. org 단위 연동이 되어 있지만 실제 분석은 로컬 checkout된 repo만 한다.
3. 로컬 `.env`와 GitHub Actions를 같이 참고해야 한다.

따라서 모델은 아래 두 축을 분리해야 한다.

### 연결 범위

1. 없음
2. repo 단위
3. org 단위

### 실행 위치

1. local
2. remote metadata only
3. hybrid

---

## 3. 데이터 모델 권장안

## 3.1 Workspace 레벨

권장 필드:

1. `workspace_type`
2. `display_name`
3. `primary_local_path`
4. `github_connection_id`
5. `default_scan_mode`

`workspace_type` 권장 enum:

1. `local_only`
2. `local_git`
3. `linked_repo`
4. `linked_org`
5. `hybrid`

## 3.2 Repository 레벨

권장 필드:

1. `source_kind`
2. `local_path`
3. `git_remote_url`
4. `github_org`
5. `github_repo`
6. `is_org_managed`

`source_kind` 권장 enum:

1. `local_untracked`
2. `local_git`
3. `github_repo`
4. `github_org_repo`

## 3.3 GitHubConnection 레벨

권장 필드:

1. `provider`
2. `account_type`
3. `account_login`
4. `installation_id`
5. `access_mode`

`access_mode` 권장 enum:

1. `repo_only`
2. `org_wide`

---

## 4. 스캔 전략

## 4.1 Repo-only scan

대상:

1. Git에 올라간 코드
2. workflow 파일
3. 빌드/테스트 설정

장점:

1. 재현 가능
2. 안전함
3. 메타데이터 수집에 유리

한계:

1. `.env.local`
2. 로컬 override
3. 실제 실행 상태

## 4.2 Workspace-local scan

대상:

1. `.env*`
2. `Makefile`
3. `docker-compose.yml`
4. `.nvmrc`
5. `.python-version`
6. 현재 브랜치
7. dirty state

장점:

1. 실제 개발 환경 반영
2. 실행 가능성 판단 정확도 상승

## 4.3 Runtime-observed scan

대상:

1. open ports
2. health endpoints
3. startup errors
4. test bootstrap 결과

장점:

1. 실제 동작 검증 가능
2. QA 자동화와 직접 연결됨

---

## 5. `.env` 처리 원칙

Local-first 도구에서는 `.env`를 읽는 것이 맞다.

다만 아래 원칙을 지킨다.

### 허용

1. 실제 값 읽기
2. 실행 시 값 활용
3. key 목록 저장
4. required 여부 저장

### 기본 금지

1. 리포트에 평문 노출
2. 로그에 평문 노출
3. DB에 민감값 평문 저장

### 권장 방식

1. 앱 내부에서는 값 사용 가능
2. persistence에는 key/metadata 위주 저장
3. 표시 시 `[REDACTED]` 마스킹

---

## 6. GitHub Actions와 로컬 워크플로

GitHub Actions는 `Automation Graph`의 핵심 입력이다.

읽어야 하는 이유:

1. 실제 테스트 명령이 들어있다.
2. 빌드 순서가 들어있다.
3. required env가 들어있다.
4. artifact 경로가 들어있다.

추출 대상:

1. workflow 이름
2. trigger
3. jobs
4. steps
5. env keys
6. artifacts

로컬 워크플로도 같이 읽어야 한다.

대상:

1. `Makefile`
2. `package.json` scripts
3. Gradle task
4. shell bootstrap scripts

즉, local-first 모델에서는 `GitHub Actions만`이 아니라 `로컬 자동화 스크립트도 동급으로 중요`하다.

---

## 7. 제품 UX 권장안

## 7.1 프로젝트 추가 화면

선택지는 다음 다섯 개가 맞다.

1. `로컬 폴더 연결`
2. `로컬 Git 레포 연결`
3. `GitHub 레포 연결`
4. `GitHub Organization 연결`
5. `로컬 + GitHub 함께 연결`

## 7.2 사이드바 그룹

권장 그룹:

1. `Local Projects`
2. `Linked Repositories`
3. `Linked Organizations`
4. `Hybrid Workspaces`

## 7.3 온보딩 후 노출 정보

1. 연결 타입
2. 로컬 경로
3. GitHub 범위
4. 감지된 service 수
5. 감지된 workflow 수
6. 로컬 env key 수

---

## 8. 최종 결론

Local-first 모델에서는 프로젝트를 다음 기준으로 분류하는 것이 맞다.

1. `GitHub 비연동`
   - `local_only`
   - `local_git`

2. `GitHub 연동`
   - `linked_repo`
   - `linked_org`

3. `혼합`
   - `hybrid`

이 분류는 DB 모델, 스캔 전략, UI, 실행 방식까지 자연스럽게 연결된다.

즉, 이 플랫폼은 다음과 같이 정의하는 것이 맞다.

`로컬 코드, 로컬 환경, GitHub 메타데이터, CI 워크플로를 함께 이해하는 local-first 자동화 플랫폼`

---

## 9. 다음 단계

이 문서 이후 실제 코드에 반영할 항목은 다음과 같다.

1. `ERD.md` 기준으로 `workspace_type`, `github_connections`, `local_workspace_bindings` 모델 추가
2. analyzer에서 local scan / repo scan / runtime scan 모드 분리
3. onboarding UI에서 5개 연결 타입 선택 가능하게 구현
