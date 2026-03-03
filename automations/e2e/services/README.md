# E2E 서비스 오케스트레이션 가이드

이 폴더 기준으로 `ora-automation`에서 서비스별 E2E를 나눠 실행합니다.

## 기본 매핑

- `b2b`: `OraB2bServer`의 e2e 패키지 테스트(Gradle)
- `android`/`b2b-android`: `OraB2bAndroid`의 Android 앱 단위 테스트(`:app:test`)
- `b2c`: `OraWebAppFrontend`의 `npm test`(또는 지정 스크립트)
- `ai`/`free`: `OraAiServer`의 `LLM_server`, `TTS_server` pytest 시나리오
- `telecom`/`ora-server`: `OraServer`의 Gradle 테스트

## 기본 실행

```bash
cd /Users/mike/workspace/side_project/Ora/ora-automation

# B2B
make e2e-service SERVICE=b2b

# B2C
make e2e-service SERVICE=b2c

# Android 앱
make e2e-service SERVICE=android

# AI(LLM/TTS)
make e2e-service SERVICE=ai

# 통신(전화)
make e2e-service SERVICE=telecom

# 4개 기본 슬롯을 한 번에
make e2e-service-all
```

## 옵션

- `E2E_CMD`: 서비스 기본 명령을 덮어쓰기
- `E2E_PYTEST_ARGS`: `ai/free` 서비스에서 pytest 인수 추가 (`tests` 기본값)
- `E2E_PROJECT_DIR`: 특정 디렉토리 강제 지정
- `E2E_FORCE_CYPRESS=1`: b2c를 Cypress 경로로 강제 실행
- `E2E_SERVICE_MODE=open|run|install`: B2C에서 Cypress 동작 모드 (`E2E_FORCE_CYPRESS` 사용 시)
- `E2E_FAIL_FAST=1`: `e2e-service-all` 실행 실패 시 즉시 중단
