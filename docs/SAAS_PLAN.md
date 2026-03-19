# Ora Automation SaaS Plan

## Overview

Ora Automation을 **데스크탑 앱 + 웹사이트** 형태로 배포하여 누구나 쉽게 사용할 수 있도록 합니다.

## 핵심 결정사항

| 항목 | 선택 |
|------|------|
| **배포 형태** | 데스크탑 앱 (Tauri) + 랜딩 웹사이트 |
| **수익 모델** | Free + 광고 (AdSense) |
| **인증** | 직접 구현 (JWT + Google OAuth) |
| **인프라** | GCP (Cloud Run) |
| **결제** | 나중에 추가 (사업자 필요 시 Stripe/Lemon Squeezy) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Landing Website                             │
│                    (ora-automation.com)                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  🎯 Hero Section                                           │  │
│  │  📥 Download Buttons (Mac / Windows / Linux)              │  │
│  │  📖 Documentation / Guides                                 │  │
│  │  💰 Google AdSense Ads                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                         Download
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Tauri Desktop App                             │
│                    (Free, No Ads)                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                                                            │  │
│  │   Existing React Frontend (No changes needed!)            │  │
│  │   - Chat Interface                                         │  │
│  │   - Organization Designer                                  │  │
│  │   - Project Manager                                        │  │
│  │   - Report Viewer                                          │  │
│  │                                                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         WebView                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                          API Calls
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Cloud Backend                              │
│                      (GCP Cloud Run)                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ FastAPI  │  │ Postgres │  │ RabbitMQ │  │ Workers  │        │
│  │  (API)   │  │   (DB)   │  │ (Queue)  │  │ (Agents) │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                              │                                   │
│                              ▼                                   │
│                       ┌──────────┐                              │
│                       │  Gemini  │                              │
│                       │   API    │                              │
│                       └──────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 수익 모델

| 채널 | 수익원 | 설명 |
|------|--------|------|
| **랜딩 웹사이트** | Google AdSense | 다운로드 페이지, 문서에 광고 |
| **데스크탑 앱** | 무료 (광고 없음) | 깔끔한 UX 제공 |
| **Pro 플랜** | 구독 (미래) | 사업자 등록 후 추가 |

### AdSense 적용 위치

```
Landing Page
├── Hero Section (광고 없음)
├── Features Section
│   └── [AdSense Banner]
├── How It Works
│   └── [AdSense Banner]
├── Download Section (광고 없음 - CTA 집중)
├── Documentation
│   └── [AdSense Sidebar]
└── Footer
    └── [AdSense Banner]
```

---

## Phase 1: Landing Website

### 기술 스택

| 항목 | 선택 | 이유 |
|------|------|------|
| Framework | **Astro** or Next.js | 정적 사이트 최적화, SEO |
| Hosting | **Vercel** or Netlify | 무료, 빠른 배포 |
| Analytics | Google Analytics | 트래픽 분석 |
| Ads | Google AdSense | 사업자 없이 가능 |

### 페이지 구성

```
/                    # 랜딩 (Hero + Features + Download)
/download            # 다운로드 페이지 (OS별 버튼)
/docs                # 문서
/docs/quickstart     # 빠른 시작 가이드
/docs/features       # 기능 설명
/changelog           # 업데이트 내역
/privacy             # 개인정보처리방침
/terms               # 이용약관
```

### 랜딩 페이지 섹션

1. **Hero**: "AI 에이전트로 R&D 자동화" + 다운로드 버튼
2. **Features**: 주요 기능 카드
3. **Demo**: 스크린샷 / GIF
4. **How it works**: 3단계 설명
5. **Download**: OS별 다운로드 버튼
6. **Footer**: 링크, 소셜

---

## Phase 2: Tauri Desktop App

### 설정 방법

```bash
# 기존 frontend 폴더에서
cd frontend
npm install -D @tauri-apps/cli @tauri-apps/api
npx tauri init
```

### 생성되는 구조

```
frontend/
├── src/                  # 기존 React (변경 없음!)
├── src-tauri/            # Tauri 설정 (새로 생성)
│   ├── Cargo.toml
│   ├── tauri.conf.json   # 앱 설정
│   ├── icons/            # 앱 아이콘
│   └── src/
│       └── main.rs       # Rust 진입점
├── package.json
└── vite.config.ts
```

### tauri.conf.json 주요 설정

```json
{
  "productName": "Ora Automation",
  "version": "1.0.0",
  "identifier": "com.ora.automation",
  "build": {
    "frontendDist": "../dist"
  },
  "app": {
    "windows": [
      {
        "title": "Ora Automation",
        "width": 1200,
        "height": 800,
        "minWidth": 800,
        "minHeight": 600
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": ["dmg", "msi", "appimage"],
    "icon": ["icons/icon.icns", "icons/icon.ico", "icons/icon.png"]
  }
}
```

### 빌드 명령어

```bash
# 개발
npm run tauri dev

# 프로덕션 빌드
npm run tauri build

# 결과물
# - macOS: .dmg (~10MB)
# - Windows: .msi (~10MB)
# - Linux: .AppImage (~10MB)
```

### 자동 업데이트 (Tauri Updater)

```json
// tauri.conf.json
{
  "plugins": {
    "updater": {
      "active": true,
      "endpoints": [
        "https://ora-automation.com/api/updates/{{target}}/{{current_version}}"
      ],
      "pubkey": "YOUR_PUBLIC_KEY"
    }
  }
}
```

---

## Phase 3: Cloud Backend (GCP)

### 서비스 구성

| 서비스 | GCP 리소스 | 스펙 | 예상 비용 |
|--------|-----------|------|----------|
| API | Cloud Run | 1 vCPU, 512MB | ~$10/월 |
| Database | Cloud SQL (Postgres) | db-f1-micro | ~$10/월 |
| Queue | Cloud Pub/Sub | - | ~$1/월 |
| Workers | Cloud Run Jobs | 2 vCPU, 1GB | 사용량 기반 |
| Storage | Cloud Storage | 리포트 저장 | ~$1/월 |

**예상 총 비용: ~$25/월**

### 배포 설정

```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/ora-api', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/ora-api']
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    args:
      - 'run'
      - 'deploy'
      - 'ora-api'
      - '--image=gcr.io/$PROJECT_ID/ora-api'
      - '--region=asia-northeast3'
      - '--platform=managed'
```

---

## Phase 4: Authentication

### 목표
- 이메일/비밀번호 회원가입 및 로그인
- Google OAuth 로그인
- JWT 토큰 기반 인증

### DB Schema

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    name VARCHAR(100),
    avatar_url TEXT,

    -- OAuth
    oauth_provider VARCHAR(20),
    oauth_id VARCHAR(255),

    -- Status
    email_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,

    UNIQUE(oauth_provider, oauth_id)
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE
);
```

### API Endpoints

```
POST /api/v1/auth/signup           # 회원가입
POST /api/v1/auth/login            # 로그인
POST /api/v1/auth/logout           # 로그아웃
POST /api/v1/auth/refresh          # 토큰 갱신
GET  /api/v1/auth/me               # 현재 사용자

GET  /api/v1/auth/google           # Google OAuth 시작
GET  /api/v1/auth/google/callback  # Google OAuth 콜백
```

---

## Phase 5: Multi-tenancy

### 데이터 격리

모든 사용자 데이터에 `user_id` 추가:

```sql
ALTER TABLE organizations ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE projects ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE conversations ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE orchestration_runs ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE scheduled_jobs ADD COLUMN user_id UUID REFERENCES users(id);
```

### API 필터링

```python
@router.get("/projects")
async def list_projects(current_user: User = Depends(get_current_user)):
    return await project_service.list_by_user(current_user.id)
```

---

## Implementation Timeline

```
Phase 1: Landing Website ─────────────────────────┐
  ├── 1.1 Astro 프로젝트 셋업                     │ Day 1
  ├── 1.2 랜딩 페이지 디자인/개발                 │ Day 1
  ├── 1.3 다운로드 페이지                         │ Day 1
  └── 1.4 AdSense 연동                            │ Day 1
                                                   │
Phase 2: Tauri Desktop App ────────────────────────┤
  ├── 2.1 Tauri 설정 추가                         │ Day 2
  ├── 2.2 아이콘 및 메타데이터                    │ Day 2
  ├── 2.3 Mac/Win/Linux 빌드                      │ Day 2
  └── 2.4 자동 업데이트 설정                      │ Day 2
                                                   │
Phase 3: Cloud Backend ────────────────────────────┤
  ├── 3.1 GCP 프로젝트 셋업                       │ Day 3
  ├── 3.2 Cloud Run 배포                          │ Day 3
  ├── 3.3 Cloud SQL 셋업                          │ Day 3
  └── 3.4 도메인 + SSL                            │ Day 3
                                                   │
Phase 4: Authentication ───────────────────────────┤
  ├── 4.1 User 모델 + 마이그레이션                │ Day 4
  ├── 4.2 회원가입/로그인 API                     │ Day 4
  ├── 4.3 JWT 토큰                                │ Day 4
  ├── 4.4 Google OAuth                            │ Day 5
  └── 4.5 데스크탑 앱 로그인 UI                   │ Day 5
                                                   │
Phase 5: Multi-tenancy ────────────────────────────┘
  ├── 5.1 기존 테이블 user_id 추가                │ Day 6
  ├── 5.2 API 필터링 적용                         │ Day 6
  └── 5.3 테스트                                  │ Day 6
```

**총 소요 시간: ~6일**

---

## Deliverables

### Phase 1 완료 시
- [ ] ora-automation.com 라이브
- [ ] 다운로드 페이지 (빈 버튼)
- [ ] AdSense 승인 신청

### Phase 2 완료 시
- [ ] Ora-Automation-1.0.0.dmg (macOS)
- [ ] Ora-Automation-1.0.0.msi (Windows)
- [ ] Ora-Automation-1.0.0.AppImage (Linux)
- [ ] 다운로드 링크 연결

### Phase 3 완료 시
- [ ] api.ora-automation.com 라이브
- [ ] 데스크탑 앱 ↔ Cloud API 연동

### Phase 4-5 완료 시
- [ ] 회원가입/로그인 동작
- [ ] 사용자별 데이터 격리

---

## Future Enhancements

### Pro 플랜 (사업자 등록 후)

| Feature | Free | Pro ($19/월) |
|---------|------|--------------|
| 분석 횟수 | 10/월 | 100/월 |
| 프로젝트 | 1개 | 무제한 |
| 에이전트 커스텀 | ❌ | ✅ |
| 우선 처리 | ❌ | ✅ |
| 이메일 리포트 | ❌ | ✅ |

### 추가 기능
- [ ] 팀 협업 (Team 플랜)
- [ ] API 액세스
- [ ] 자체 호스팅 옵션
- [ ] 플러그인 시스템

---

## 다음 단계

**Phase 1부터 시작:**

1. Astro 프로젝트 생성
2. 랜딩 페이지 개발
3. Vercel 배포
4. AdSense 신청
