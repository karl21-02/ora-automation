# GitHub App Integration Plan

> Ora Automation에 GitHub App 연동 + 통합 프로젝트 관리 시스템

## 개요

GitHub App을 통해 사용자의 Organization/Repository를 동기화하고, 로컬 워크스페이스 스캔과 통합하여 R&D 분석 대상으로 활용합니다.

### 핵심 기능

1. **GitHub App 연동** - Org/Repo 동기화
2. **로컬 워크스페이스 스캔** - 기존 클론된 레포 감지
3. **GitHub ↔ 로컬 매칭** - remote URL로 자동 연결
4. **On-demand Clone** - 필요 시 자동 shallow clone
5. **통합 프로젝트 관리** - 모든 소스를 하나의 테이블로

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

## 통합 프로젝트 아키텍처

### 전체 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                      Project Sources                         │
├──────────────────┬──────────────────┬───────────────────────┤
│  Local Workspace │   GitHub Sync    │   On-demand Clone     │
│  (기존 스캔)      │   (새 기능)       │   (자동)              │
│                  │                  │                       │
│  ~/workspace/    │  GitHub App →    │  GitHub repo URL →    │
│  Ora/OraAi/...   │  Repo 목록 동기화  │  shallow clone        │
└────────┬─────────┴────────┬─────────┴───────────┬───────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Unified Projects Table                    │
│                                                              │
│  id | name | source_type | local_path | github_repo_id | .. │
│  ───┼──────┼─────────────┼────────────┼─────────────────┼─── │
│  1  │ Ora  │ local       │ ~/work/Ora │ null            │    │
│  2  │ API  │ github      │ ~/clone/.. │ gh_repo_123     │    │
│  3  │ Lib  │ github_only │ null       │ gh_repo_456     │    │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Analysis Pipeline                         │
│                                                              │
│  - local_path 있으면 → 직접 분석                              │
│  - local_path 없으면 → shallow clone 후 분석                  │
└─────────────────────────────────────────────────────────────┘
```

### Source Type 정의

| source_type | 설명 | local_path | github_repo_id | 분석 방법 |
|-------------|------|------------|----------------|----------|
| `local` | 로컬만 존재 | ✅ | ❌ | 직접 분석 |
| `github` | GitHub + 로컬 연결됨 | ✅ | ✅ | 직접 분석 |
| `github_only` | GitHub만 (clone 필요) | ❌ | ✅ | shallow clone 후 분석 |

### 로컬 ↔ GitHub 매칭 로직

```python
# 로컬 워크스페이스 스캔 시
# 1. 각 폴더의 .git/config에서 remote origin URL 추출
# 2. GitHub 동기화된 repo와 URL 비교
# 3. 매칭되면 local_path 연결

def extract_remote_url(repo_path: str) -> str | None:
    """Git repo에서 origin remote URL 추출"""
    config_path = os.path.join(repo_path, ".git", "config")
    # parse [remote "origin"] url = ...

def match_github_repos(local_repos: list, github_repos: list):
    """로컬 repo와 GitHub repo 매칭"""
    for local in local_repos:
        remote_url = extract_remote_url(local["path"])
        if not remote_url:
            continue

        # URL 정규화 (https/ssh 형식 통일)
        normalized = normalize_github_url(remote_url)

        for gh_repo in github_repos:
            if normalize_github_url(gh_repo.clone_url) == normalized:
                # 매칭 성공!
                yield {
                    "local_path": local["path"],
                    "github_repo_id": gh_repo.id,
                    "source_type": "github",
                }
                break
        else:
            # GitHub에 없는 로컬 repo
            yield {
                "local_path": local["path"],
                "github_repo_id": None,
                "source_type": "local",
            }
```

---

## GitHub App 아키텍처

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

class Project(Base):
    """통합 프로젝트 테이블 - 모든 분석 대상의 단일 소스"""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # Source type: "local", "github", "github_only"
    source_type: Mapped[str] = mapped_column(String(20), default="local")

    # Local path (if available)
    local_path: Mapped[str | None] = mapped_column(String(500))

    # GitHub connection (if synced)
    github_repo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("github_repos.id", ondelete="SET NULL")
    )

    # Analysis settings
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    analysis_count: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata (cached from GitHub or local scan)
    language: Mapped[str | None] = mapped_column(String(50))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    github_repo: Mapped["GithubRepo | None"] = relationship(back_populates="project")


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

    # Timestamps
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    installation: Mapped["GithubInstallation"] = relationship(back_populates="repos")
    project: Mapped["Project | None"] = relationship(back_populates="github_repo")
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

### Phase 2: 로컬 워크스페이스 스캔

#### 2.1 Local Scanner

```python
# local_scanner.py

import os
import configparser
from pathlib import Path

def scan_local_workspace(workspace_path: str) -> list[dict]:
    """로컬 워크스페이스에서 Git 레포 스캔"""
    repos = []
    workspace = Path(workspace_path)

    for item in workspace.iterdir():
        if not item.is_dir():
            continue

        git_dir = item / ".git"
        if not git_dir.exists():
            continue

        remote_url = extract_git_remote(item)
        language = detect_primary_language(item)

        repos.append({
            "name": item.name,
            "path": str(item.absolute()),
            "remote_url": remote_url,
            "language": language,
        })

    return repos


def extract_git_remote(repo_path: Path) -> str | None:
    """Git config에서 origin remote URL 추출"""
    config_path = repo_path / ".git" / "config"
    if not config_path.exists():
        return None

    config = configparser.ConfigParser()
    config.read(config_path)

    try:
        return config.get('remote "origin"', "url")
    except (configparser.NoSectionError, configparser.NoOptionError):
        return None


def normalize_github_url(url: str) -> str:
    """GitHub URL 정규화 (https/ssh 통일)"""
    # git@github.com:owner/repo.git -> github.com/owner/repo
    # https://github.com/owner/repo.git -> github.com/owner/repo
    url = url.replace("git@github.com:", "github.com/")
    url = url.replace("https://github.com/", "github.com/")
    url = url.replace("http://github.com/", "github.com/")
    url = url.rstrip(".git")
    return url.lower()


def detect_primary_language(repo_path: Path) -> str | None:
    """레포의 주요 언어 감지"""
    extensions = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
    }

    counts = {}
    for ext, lang in extensions.items():
        count = len(list(repo_path.rglob(f"*{ext}")))
        if count > 0:
            counts[lang] = counts.get(lang, 0) + count

    if not counts:
        return None
    return max(counts, key=counts.get)
```

#### 2.2 프로젝트 동기화 서비스

```python
# project_service.py

async def sync_local_workspace(workspace_path: str, db: Session) -> dict:
    """로컬 워크스페이스 스캔 및 프로젝트 동기화"""
    local_repos = scan_local_workspace(workspace_path)
    github_repos = db.query(GithubRepo).all()

    created, updated, unchanged = 0, 0, 0

    for local in local_repos:
        # 기존 프로젝트 찾기 (local_path로)
        existing = db.query(Project).filter(
            Project.local_path == local["path"]
        ).first()

        # GitHub 매칭 시도
        github_match = None
        if local["remote_url"]:
            normalized = normalize_github_url(local["remote_url"])
            for gh in github_repos:
                if normalize_github_url(gh.clone_url) == normalized:
                    github_match = gh
                    break

        if existing:
            # 업데이트
            if github_match and not existing.github_repo_id:
                existing.github_repo_id = github_match.id
                existing.source_type = "github"
                updated += 1
            else:
                unchanged += 1
        else:
            # 새로 생성
            project = Project(
                id=uuid4().hex,
                name=local["name"],
                local_path=local["path"],
                language=local["language"],
                source_type="github" if github_match else "local",
                github_repo_id=github_match.id if github_match else None,
            )
            db.add(project)
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "unchanged": unchanged}
```

### Phase 3: API 엔드포인트

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


# projects_router.py - 통합 프로젝트 API

projects_router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

@projects_router.get("", response_model=list[ProjectRead])
def list_projects(
    source_type: str | None = None,  # "local", "github", "github_only"
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    """통합 프로젝트 목록"""
    query = db.query(Project)
    if source_type:
        query = query.filter(Project.source_type == source_type)
    if enabled_only:
        query = query.filter(Project.enabled == True)
    return query.order_by(Project.name).all()

@projects_router.post("/scan-local")
async def scan_local(
    workspace_path: str = Query(default=None),
    db: Session = Depends(get_db),
):
    """로컬 워크스페이스 스캔 및 프로젝트 동기화"""
    path = workspace_path or settings.ora_projects_root
    result = await sync_local_workspace(path, db)
    return result

@projects_router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    """프로젝트 설정 업데이트"""
    pass

@projects_router.post("/{project_id}/prepare")
async def prepare_project(project_id: str, db: Session = Depends(get_db)):
    """분석을 위한 프로젝트 준비 (필요시 clone)"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "project not found")

    local_path = await ensure_local_path(project, db)
    return {"local_path": local_path}
```

### Phase 4: On-demand Clone

```python
# clone_service.py

import asyncio
import shutil
from pathlib import Path

CLONE_BASE_DIR = Path("/tmp/ora-clones")


async def ensure_local_path(project: Project, db: Session) -> str:
    """프로젝트의 로컬 경로 확보 (필요시 clone)"""

    # 이미 로컬 경로가 있고 존재하면 그대로 사용
    if project.local_path and Path(project.local_path).exists():
        return project.local_path

    # GitHub repo가 없으면 에러
    if not project.github_repo:
        raise ValueError("No local path and no GitHub repo linked")

    # Clone 경로 결정
    clone_path = CLONE_BASE_DIR / project.github_repo.full_name
    clone_path.parent.mkdir(parents=True, exist_ok=True)

    # 이미 clone되어 있으면 pull
    if clone_path.exists():
        await git_pull(clone_path)
    else:
        await shallow_clone(project.github_repo.clone_url, clone_path)

    # 프로젝트에 local_path 업데이트
    project.local_path = str(clone_path)
    db.commit()

    return str(clone_path)


async def shallow_clone(clone_url: str, target_path: Path) -> None:
    """Shallow clone 실행"""
    cmd = [
        "git", "clone",
        "--depth", "1",
        "--single-branch",
        clone_url,
        str(target_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Clone failed: {stderr.decode()}")


async def git_pull(repo_path: Path) -> None:
    """기존 repo에서 pull"""
    proc = await asyncio.create_subprocess_exec(
        "git", "pull", "--ff-only",
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


def cleanup_old_clones(max_age_days: int = 7) -> int:
    """오래된 clone 정리"""
    import time
    cutoff = time.time() - (max_age_days * 86400)
    removed = 0

    for path in CLONE_BASE_DIR.glob("*/*"):
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path)
            removed += 1

    return removed
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

## 구현 순서 요약

### Phase 1: 백엔드 기반 (GitHub App 설정)
- [ ] GitHub App 생성 (GitHub 웹에서)
- [ ] 환경 변수 설정
- [ ] DB 모델 (`Project`, `GithubInstallation`, `GithubRepo`)
- [ ] GitHub 클라이언트 (`github_client.py`)

### Phase 2: 로컬 워크스페이스 스캔
- [ ] `local_scanner.py` - 로컬 Git repo 스캔
- [ ] `project_service.py` - 프로젝트 동기화
- [ ] GitHub URL 매칭 로직

### Phase 3: API 엔드포인트
- [ ] `github_router.py` - GitHub 관련 API
- [ ] `projects_router.py` - 통합 프로젝트 API
- [ ] Webhook 처리

### Phase 4: On-demand Clone
- [ ] `clone_service.py` - shallow clone / pull
- [ ] `ensure_local_path()` - 분석 전 경로 확보
- [ ] 임시 clone 정리 스케줄러

### Phase 5: 프론트엔드
- [ ] 설정 패널 GitHub 섹션
- [ ] 프로젝트 목록 (통합 뷰)
- [ ] 로컬 스캔 / GitHub 동기화 버튼

### Phase 6: 서비스 연동
- [ ] 채팅에서 프로젝트 선택 연동
- [ ] 오케스트레이션 실행 시 `ensure_local_path()` 호출

---

## API 엔드포인트 요약 (최종)

### GitHub 연동
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/github/install-url` | App 설치 URL |
| POST | `/api/v1/github/webhook` | Webhook 수신 |
| GET | `/api/v1/github/installations` | 설치 목록 |
| POST | `/api/v1/github/installations/{id}/sync` | Repo 동기화 |
| DELETE | `/api/v1/github/installations/{id}` | 연결 해제 |
| GET | `/api/v1/github/repos` | GitHub Repo 목록 |

### 통합 프로젝트
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/projects` | 프로젝트 목록 |
| POST | `/api/v1/projects/scan-local` | 로컬 스캔 |
| PATCH | `/api/v1/projects/{id}` | 설정 변경 |
| POST | `/api/v1/projects/{id}/prepare` | 분석 준비 (clone) |
