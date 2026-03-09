# GitHub App Integration Plan

> Ora Automation에 GitHub App 연동 기능 추가

## 개요

GitHub App을 통해 사용자의 Organization/Repository를 동기화하고, 이를 R&D 분석 대상으로 활용합니다.

### 왜 GitHub App인가?

| 방식 | UX | 보안 | Rate Limit | 추천 |
|------|-----|------|------------|------|
| Personal Access Token | 토큰 복붙 | 노출 위험 | 5,000/hr | X |
| GitHub OAuth | 로그인 버튼 | 안전 | 5,000/hr | △ |
| **GitHub App** | Install 버튼 | 가장 안전 | **15,000/hr** | **O** |

GitHub App 장점:
- Org 단위 설치 (팀 전체 사용)
- 높은 API Rate Limit
- Webhook 자동 지원
- 세밀한 권한 제어
- 전문적인 UX

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  Ora GitHub  │───>│  Webhook     │───>│  Installation│       │
│  │  App         │    │  Events      │    │  on Org/Repo │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │                    ▼                    │
         │         ┌──────────────────┐            │
         │         │  POST /webhook   │            │
         │         │  (installation   │            │
         │         │   created/deleted)│           │
         │         └──────────────────┘            │
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Ora Backend                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ github_router│    │github_client │    │   Models     │       │
│  │              │───>│ (PyGithub)   │───>│ Installation │       │
│  │ /api/v1/     │    │              │    │ GithubRepo   │       │
│  │   github/*   │    └──────────────┘    └──────────────┘       │
│  └──────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

### 데이터 흐름

1. 사용자가 "GitHub 연결" 버튼 클릭
2. GitHub App 설치 페이지로 이동
3. 사용자가 Org/Repo 선택 후 설치 승인
4. GitHub → Ora Webhook: `installation.created` 이벤트
5. Ora가 Installation 정보 저장
6. 사용자가 "동기화" 클릭 → Repo 목록 가져와서 저장
7. 동기화된 Repo를 분석 대상으로 선택 가능

---

## 구현 계획

### Phase 1: GitHub App 설정 & 백엔드 기반

#### 1.1 GitHub App 생성 (수동)

GitHub에서 App 생성 시 필요한 설정:

```yaml
App Name: Ora Automation
Homepage URL: https://your-domain.com
Webhook URL: https://your-domain.com/api/v1/github/webhook
Webhook Secret: <random-string>

Permissions:
  Repository:
    - Contents: Read
    - Metadata: Read
  Organization:
    - Members: Read (optional)

Subscribe to events:
  - Installation
  - Repository
```

#### 1.2 환경 변수

```bash
# .env
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
GITHUB_WEBHOOK_SECRET=your-webhook-secret
GITHUB_APP_NAME=ora-automation
```

#### 1.3 DB 모델

```python
# models.py

class GithubInstallation(Base):
    """GitHub App이 설치된 Org/User 정보"""
    __tablename__ = "github_installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    account_type: Mapped[str] = mapped_column(String(20))  # "Organization" or "User"
    account_login: Mapped[str] = mapped_column(String(255))  # org name or username
    account_id: Mapped[int] = mapped_column(BigInteger)
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, suspended, deleted

    # Timestamps
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    repos: Mapped[list["GithubRepo"]] = relationship(back_populates="installation", cascade="all, delete-orphan")


class GithubRepo(Base):
    """동기화된 GitHub Repository"""
    __tablename__ = "github_repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(36), ForeignKey("github_installations.id", ondelete="CASCADE"))

    # GitHub repo info
    repo_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(500))  # owner/repo
    description: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str] = mapped_column(String(500))
    clone_url: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")

    # Metadata
    language: Mapped[str | None] = mapped_column(String(50))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ora integration
    enabled_for_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Timestamps
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    installation: Mapped["GithubInstallation"] = relationship(back_populates="repos")
```

#### 1.4 GitHub 클라이언트

```python
# github_client.py

import jwt
import time
import httpx
from functools import lru_cache

class GitHubAppClient:
    """GitHub App API 클라이언트"""

    def __init__(self, app_id: str, private_key: str):
        self.app_id = app_id
        self.private_key = private_key
        self.base_url = "https://api.github.com"

    def _generate_jwt(self) -> str:
        """App 인증용 JWT 생성 (10분 유효)"""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # 1분 전
            "exp": now + 600,  # 10분 후
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        """Installation용 액세스 토큰 발급"""
        jwt_token = self._generate_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            return resp.json()["token"]

    async def list_installation_repos(self, installation_id: int) -> list[dict]:
        """Installation에 접근 가능한 모든 Repo 목록"""
        token = await self.get_installation_token(installation_id)
        repos = []
        page = 1

        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{self.base_url}/installation/repositories",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                data = resp.json()
                repos.extend(data["repositories"])

                if len(data["repositories"]) < 100:
                    break
                page += 1

        return repos
```

### Phase 2: API 엔드포인트

```python
# github_router.py

router = APIRouter(prefix="/api/v1/github", tags=["github"])

@router.get("/install-url")
def get_install_url() -> dict:
    """GitHub App 설치 URL 반환"""
    app_name = settings.github_app_name
    return {
        "url": f"https://github.com/apps/{app_name}/installations/new"
    }

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    """GitHub Webhook 수신"""
    # 1. Signature 검증
    # 2. Event 타입에 따라 처리
    #    - installation.created → Installation 저장
    #    - installation.deleted → Installation 삭제
    #    - repository.added → Repo 추가
    #    - repository.removed → Repo 삭제
    pass

@router.get("/installations", response_model=list[GithubInstallationRead])
def list_installations(db: Session = Depends(get_db)):
    """연결된 GitHub 설치 목록"""
    return db.query(GithubInstallation).filter(
        GithubInstallation.status == "active"
    ).all()

@router.post("/installations/{installation_id}/sync")
async def sync_installation(installation_id: str, db: Session = Depends(get_db)):
    """특정 Installation의 Repo 동기화"""
    pass

@router.get("/repos", response_model=list[GithubRepoRead])
def list_repos(
    installation_id: str | None = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    """동기화된 Repo 목록"""
    pass

@router.patch("/repos/{repo_id}")
def update_repo(repo_id: str, payload: GithubRepoUpdate, db: Session = Depends(get_db)):
    """Repo 설정 업데이트 (분석 활성화 등)"""
    pass
```

### Phase 3: 프론트엔드

#### 3.1 설정 패널 GitHub 섹션

```tsx
// components/GitHubSettings.tsx

export default function GitHubSettings() {
  const [installations, setInstallations] = useState<GithubInstallation[]>([])
  const [syncing, setSyncing] = useState<string | null>(null)

  return (
    <div>
      <h3>GitHub 연동</h3>

      {/* 설치 버튼 */}
      <button onClick={() => window.open(installUrl, '_blank')}>
        <GithubIcon /> GitHub App 설치
      </button>

      {/* 연결된 Org 목록 */}
      {installations.map(inst => (
        <div key={inst.id}>
          <img src={inst.avatar_url} />
          <span>{inst.account_login}</span>
          <span>{inst.repos_count} repos</span>
          <button onClick={() => handleSync(inst.id)}>
            {syncing === inst.id ? 'Syncing...' : 'Sync'}
          </button>
        </div>
      ))}
    </div>
  )
}
```

#### 3.2 Repo 목록 & 분석 활성화

```tsx
// components/GitHubRepoList.tsx

export default function GitHubRepoList() {
  const [repos, setRepos] = useState<GithubRepo[]>([])

  return (
    <div>
      {repos.map(repo => (
        <div key={repo.id}>
          <span>{repo.full_name}</span>
          <span>{repo.language}</span>
          <Toggle
            checked={repo.enabled_for_analysis}
            onChange={() => toggleAnalysis(repo.id)}
          />
        </div>
      ))}
    </div>
  )
}
```

### Phase 4: 서비스 연동

#### 4.1 채팅에서 GitHub Repo 분석

```python
# dialog_engine.py 수정

# "OraAiServer 분석해줘" 입력 시
# 1. github_repos 테이블에서 매칭되는 repo 검색
# 2. 해당 repo의 clone_url을 사용해 분석 실행
```

#### 4.2 프로젝트 선택 UI에 GitHub Repo 포함

```tsx
// 기존 프로젝트 목록 + GitHub Repo 통합 표시
// 아이콘으로 구분 (📁 로컬, 🐙 GitHub)
```

---

## 환경 변수 요약

```bash
# GitHub App 설정
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----..."
GITHUB_WEBHOOK_SECRET=whsec_xxxxx
GITHUB_APP_NAME=ora-automation

# Optional
GITHUB_API_BASE_URL=https://api.github.com  # Enterprise는 변경
```

---

## DB 마이그레이션

```sql
-- github_installations 테이블
CREATE TABLE github_installations (
    id VARCHAR(36) PRIMARY KEY,
    installation_id BIGINT UNIQUE NOT NULL,
    account_type VARCHAR(20) NOT NULL,
    account_login VARCHAR(255) NOT NULL,
    account_id BIGINT NOT NULL,
    avatar_url VARCHAR(500),
    status VARCHAR(20) DEFAULT 'active',
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    synced_at TIMESTAMP
);

-- github_repos 테이블
CREATE TABLE github_repos (
    id VARCHAR(36) PRIMARY KEY,
    installation_id VARCHAR(36) REFERENCES github_installations(id) ON DELETE CASCADE,
    repo_id BIGINT UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(500) NOT NULL,
    description TEXT,
    html_url VARCHAR(500) NOT NULL,
    clone_url VARCHAR(500) NOT NULL,
    default_branch VARCHAR(100) DEFAULT 'main',
    language VARCHAR(50),
    stars INTEGER DEFAULT 0,
    is_private BOOLEAN DEFAULT FALSE,
    enabled_for_analysis BOOLEAN DEFAULT TRUE,
    last_analyzed_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_github_repos_installation ON github_repos(installation_id);
CREATE INDEX idx_github_repos_full_name ON github_repos(full_name);
```

---

## API 엔드포인트 요약

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/github/install-url` | App 설치 URL |
| POST | `/api/v1/github/webhook` | Webhook 수신 |
| GET | `/api/v1/github/installations` | 설치 목록 |
| POST | `/api/v1/github/installations/{id}/sync` | Repo 동기화 |
| DELETE | `/api/v1/github/installations/{id}` | 연결 해제 |
| GET | `/api/v1/github/repos` | Repo 목록 |
| PATCH | `/api/v1/github/repos/{id}` | Repo 설정 변경 |

---

## 보안 고려사항

1. **Webhook Signature 검증** - `X-Hub-Signature-256` 헤더로 요청 검증
2. **Private Key 보관** - 환경 변수 또는 Secret Manager 사용
3. **Installation Token** - 1시간 만료, 필요 시 재발급
4. **최소 권한 원칙** - 필요한 권한만 요청 (Contents: Read, Metadata: Read)

---

## 다음 단계

1. [ ] GitHub App 생성 (GitHub 웹에서)
2. [ ] Phase 1: 백엔드 기반 구현
3. [ ] Phase 2: API 엔드포인트 구현
4. [ ] Phase 3: 프론트엔드 구현
5. [ ] Phase 4: 서비스 연동
6. [ ] 테스트 & 배포
