# Control Center 개발 스펙

> 프로젝트 소스 관리 및 통합 대시보드

## 1. 개요

### 1.1 목적
- 로컬 워크스페이스 + GitHub 레포를 통합 관리
- 프로젝트별 환경설정(.env), 분석 이력 조회
- R&D 분석 대상 프로젝트 중앙 관리

### 1.2 UI 구조

```
┌────────────┬─────────────┬──────────────────────────────┐
│ Main Menu  │ Sub Panel   │     Main Content             │
│ (항상 유지) │ (Control용) │                              │
├────────────┼─────────────┼──────────────────────────────┤
│            │             │                              │
│ 💬 Chats   │ 📁 Sources  │   📋 ora-automation          │
│ 📄 Reports │  └ ~/work   │                              │
│ 🏢 Orgs    │  └ GitHub   │   Overview | .env | Config   │
│ 🎛️ Control │─────────────│   ─────────────────────────  │
│ ⏰ Sched   │ 📦 Projects │   DATABASE_URL=postgres://.. │
│ ⚙️ Settings│  • ora-auto │   GITHUB_APP_ID=123456       │
│            │  • ora-ai   │   API_SECRET=••••••••        │
│            │  • ora-web  │                              │
│            │             │   [▶️ 분석] [⚙️ 설정]         │
└────────────┴─────────────┴──────────────────────────────┘
     60px        220px              나머지
```

### 1.3 핵심 기능
1. **Sources 관리**: 로컬 경로 + GitHub 연동
2. **Projects 목록**: 통합 프로젝트 리스트
3. **Project Detail**: 상세 정보 + .env + 분석 이력

---

## 2. 데이터 모델

### 2.1 ScanPath (스캔 경로)

```python
class ScanPath(Base):
    """사용자가 등록한 로컬 스캔 경로"""
    __tablename__ = "scan_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # 경로 정보
    path: Mapped[str] = mapped_column(String(500), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))  # 별칭: "회사", "개인"

    # 설정
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recursive: Mapped[bool] = mapped_column(Boolean, default=False)  # 하위 폴더 스캔

    # 상태
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime)
    project_count: Mapped[int] = mapped_column(Integer, default=0)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=func.now())
```

### 2.2 Project (통합 프로젝트)

```python
class Project(Base):
    """통합 프로젝트 - 모든 분석 대상"""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # 기본 정보
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # 소스 타입: "local", "github", "github_only"
    source_type: Mapped[str] = mapped_column(String(20), default="local")

    # 로컬 경로 (있으면)
    local_path: Mapped[str | None] = mapped_column(String(500))
    scan_path_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scan_paths.id", ondelete="SET NULL")
    )

    # GitHub 연결 (있으면)
    github_repo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("github_repos.id", ondelete="SET NULL")
    )

    # 메타데이터
    language: Mapped[str | None] = mapped_column(String(50))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")

    # 분석 설정
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    analysis_count: Mapped[int] = mapped_column(Integer, default=0)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=func.now())

    # 관계
    scan_path: Mapped["ScanPath | None"] = relationship()
    github_repo: Mapped["GithubRepo | None"] = relationship(back_populates="project")
```

### 2.3 GithubInstallation (GitHub 설치)

```python
class GithubInstallation(Base):
    """GitHub App 설치 정보"""
    __tablename__ = "github_installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # GitHub 정보
    installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    account_type: Mapped[str] = mapped_column(String(20))  # "Organization" | "User"
    account_login: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[int] = mapped_column(BigInteger)
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    # 상태
    status: Mapped[str] = mapped_column(String(20), default="active")

    # 타임스탬프
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 관계
    repos: Mapped[list["GithubRepo"]] = relationship(back_populates="installation")
```

### 2.4 GithubRepo (GitHub 레포)

```python
class GithubRepo(Base):
    """GitHub 레포지토리"""
    __tablename__ = "github_repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # 연결
    installation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("github_installations.id", ondelete="CASCADE")
    )

    # GitHub 정보
    repo_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(500))  # owner/repo
    description: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str] = mapped_column(String(500))
    clone_url: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")

    # 메타데이터
    language: Mapped[str | None] = mapped_column(String(50))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)

    # 타임스탬프
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # 관계
    installation: Mapped["GithubInstallation"] = relationship(back_populates="repos")
    project: Mapped["Project | None"] = relationship(back_populates="github_repo")
```

### 2.5 ER 다이어그램

```
┌─────────────┐       ┌─────────────┐       ┌──────────────────┐
│  ScanPath   │       │   Project   │       │ GithubInstallation│
├─────────────┤       ├─────────────┤       ├──────────────────┤
│ id          │──┐    │ id          │    ┌──│ id               │
│ path        │  │    │ name        │    │  │ installation_id  │
│ name        │  └───>│ source_type │    │  │ account_login    │
│ enabled     │       │ local_path  │    │  │ status           │
│ recursive   │       │ scan_path_id│────┘  └──────────────────┘
└─────────────┘       │ github_repo_id│────┐          │
                      │ language    │    │          │
                      │ enabled     │    │          ▼
                      └─────────────┘    │  ┌─────────────┐
                                         │  │ GithubRepo  │
                                         │  ├─────────────┤
                                         └─>│ id          │
                                            │ full_name   │
                                            │ clone_url   │
                                            │ language    │
                                            └─────────────┘
```

---

## 3. API 엔드포인트

### 3.1 Scan Paths API

```
POST   /api/v1/scan-paths              스캔 경로 추가
GET    /api/v1/scan-paths              스캔 경로 목록
GET    /api/v1/scan-paths/{id}         스캔 경로 상세
PATCH  /api/v1/scan-paths/{id}         스캔 경로 수정
DELETE /api/v1/scan-paths/{id}         스캔 경로 삭제
POST   /api/v1/scan-paths/{id}/scan    특정 경로 스캔 실행
POST   /api/v1/scan-paths/scan-all     전체 스캔 실행
```

#### 스키마

```python
class ScanPathCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
    name: str | None = Field(default=None, max_length=100)
    recursive: bool = False

class ScanPathRead(BaseModel):
    id: str
    path: str
    name: str | None
    enabled: bool
    recursive: bool
    last_scanned_at: datetime | None
    project_count: int
    created_at: datetime

class ScanPathUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    recursive: bool | None = None

class ScanResult(BaseModel):
    scan_path_id: str
    projects_found: int
    projects_created: int
    projects_updated: int
    duration_ms: int
```

### 3.2 Projects API

```
GET    /api/v1/projects                프로젝트 목록
GET    /api/v1/projects/{id}           프로젝트 상세
PATCH  /api/v1/projects/{id}           프로젝트 수정
DELETE /api/v1/projects/{id}           프로젝트 삭제
POST   /api/v1/projects/{id}/prepare   분석 준비 (clone)
GET    /api/v1/projects/{id}/env       .env 파일 조회
GET    /api/v1/projects/{id}/config    설정 파일 조회
GET    /api/v1/projects/{id}/history   분석 이력 조회
```

#### 스키마

```python
class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None
    source_type: str  # "local" | "github" | "github_only"
    local_path: str | None
    language: str | None
    default_branch: str
    enabled: bool
    last_analyzed_at: datetime | None
    analysis_count: int
    created_at: datetime

    # 연결 정보
    scan_path: ScanPathRead | None
    github_repo: GithubRepoRead | None

class ProjectUpdate(BaseModel):
    enabled: bool | None = None
    default_branch: str | None = None

class ProjectEnvResponse(BaseModel):
    has_env: bool
    has_env_example: bool
    env_content: dict[str, str]  # key -> value (마스킹된)
    env_example_content: dict[str, str] | None

class ProjectConfigResponse(BaseModel):
    files: list[ConfigFile]

class ConfigFile(BaseModel):
    name: str  # "package.json", "pyproject.toml"
    path: str
    content: dict | str

class AnalysisHistoryItem(BaseModel):
    id: str
    run_type: str  # "rd_analysis", "security", etc.
    status: str
    started_at: datetime
    completed_at: datetime | None
    report_path: str | None
```

### 3.3 GitHub API

```
GET    /api/v1/github/install-url               App 설치 URL
POST   /api/v1/github/webhook                   Webhook 수신
GET    /api/v1/github/installations             설치 목록
POST   /api/v1/github/installations/{id}/sync   레포 동기화
DELETE /api/v1/github/installations/{id}        연결 해제
GET    /api/v1/github/repos                     GitHub 레포 목록
```

---

## 4. 프론트엔드 구조

### 4.1 컴포넌트 트리

```
frontend/src/
├── components/
│   ├── ControlCenter/
│   │   ├── ControlCenter.tsx          # 메인 컨테이너
│   │   ├── ControlSubPanel.tsx        # 2단 사이드바 (Sources + Projects)
│   │   ├── SourceList.tsx             # 소스 목록 (ScanPaths + GitHub)
│   │   ├── ScanPathItem.tsx           # 스캔 경로 아이템
│   │   ├── GitHubInstallItem.tsx      # GitHub 설치 아이템
│   │   ├── ProjectList.tsx            # 프로젝트 목록
│   │   ├── ProjectItem.tsx            # 프로젝트 아이템
│   │   ├── ProjectDetail.tsx          # 프로젝트 상세 (메인)
│   │   ├── ProjectOverview.tsx        # Overview 탭
│   │   ├── ProjectEnvViewer.tsx       # .env 탭
│   │   ├── ProjectConfigViewer.tsx    # Config 탭
│   │   ├── ProjectHistory.tsx         # Analysis History 탭
│   │   ├── AddScanPathModal.tsx       # 경로 추가 모달
│   │   └── index.ts
│   └── ...
├── lib/
│   └── api.ts                          # API 함수 추가
└── types.ts                            # 타입 추가
```

### 4.2 ControlCenter.tsx (메인)

```tsx
interface ControlCenterProps {
  // 없음 - 독립 컴포넌트
}

export default function ControlCenter() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [scanPaths, setScanPaths] = useState<ScanPath[]>([])
  const [githubInstalls, setGithubInstalls] = useState<GithubInstallation[]>([])
  const [projects, setProjects] = useState<Project[]>([])

  return (
    <div style={{ display: 'flex', flex: 1, height: '100%' }}>
      {/* 2단 사이드바 */}
      <ControlSubPanel
        scanPaths={scanPaths}
        githubInstalls={githubInstalls}
        projects={projects}
        selectedProjectId={selectedProjectId}
        onSelectProject={setSelectedProjectId}
        onRefresh={loadData}
      />

      {/* 메인 컨텐츠 */}
      {selectedProjectId ? (
        <ProjectDetail projectId={selectedProjectId} />
      ) : (
        <EmptyState message="프로젝트를 선택하세요" />
      )}
    </div>
  )
}
```

### 4.3 ControlSubPanel.tsx (2단 사이드바)

```tsx
export default function ControlSubPanel({
  scanPaths,
  githubInstalls,
  projects,
  selectedProjectId,
  onSelectProject,
  onRefresh,
}: Props) {
  const [showAddPath, setShowAddPath] = useState(false)

  return (
    <div style={subPanelStyle}>
      {/* Sources 섹션 */}
      <Section title="SOURCES">
        <SectionHeader>
          <span>📁 Local Paths</span>
          <button onClick={() => setShowAddPath(true)}>+</button>
        </SectionHeader>
        {scanPaths.map(sp => (
          <ScanPathItem key={sp.id} scanPath={sp} onScan={...} />
        ))}

        <SectionHeader>
          <span>🐙 GitHub</span>
          <button onClick={openGitHubInstall}>+</button>
        </SectionHeader>
        {githubInstalls.map(gi => (
          <GitHubInstallItem key={gi.id} install={gi} onSync={...} />
        ))}
      </Section>

      <Divider />

      {/* Projects 섹션 */}
      <Section title={`PROJECTS (${projects.length})`}>
        <SearchInput placeholder="Search projects..." />
        <ProjectList
          projects={projects}
          selectedId={selectedProjectId}
          onSelect={onSelectProject}
        />
      </Section>

      {/* 모달 */}
      {showAddPath && (
        <AddScanPathModal onClose={() => setShowAddPath(false)} onAdd={...} />
      )}
    </div>
  )
}

const subPanelStyle: React.CSSProperties = {
  width: 220,
  borderRight: '1px solid #e5e7eb',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}
```

### 4.4 ProjectDetail.tsx (상세)

```tsx
type Tab = 'overview' | 'env' | 'config' | 'history'

export default function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadProject(projectId)
  }, [projectId])

  return (
    <div style={detailStyle}>
      {/* 헤더 */}
      <Header>
        <h2>{project?.name}</h2>
        <SourceBadge type={project?.source_type} />
        <Spacer />
        <Button onClick={runAnalysis}>▶️ 분석 실행</Button>
        <Button onClick={openSettings}>⚙️</Button>
      </Header>

      {/* 탭 */}
      <TabBar>
        <Tab active={activeTab === 'overview'} onClick={() => setActiveTab('overview')}>
          Overview
        </Tab>
        <Tab active={activeTab === 'env'} onClick={() => setActiveTab('env')}>
          .env
        </Tab>
        <Tab active={activeTab === 'config'} onClick={() => setActiveTab('config')}>
          Config
        </Tab>
        <Tab active={activeTab === 'history'} onClick={() => setActiveTab('history')}>
          History
        </Tab>
      </TabBar>

      {/* 탭 컨텐츠 */}
      <TabContent>
        {activeTab === 'overview' && <ProjectOverview project={project} />}
        {activeTab === 'env' && <ProjectEnvViewer projectId={projectId} />}
        {activeTab === 'config' && <ProjectConfigViewer projectId={projectId} />}
        {activeTab === 'history' && <ProjectHistory projectId={projectId} />}
      </TabContent>
    </div>
  )
}
```

### 4.5 ProjectEnvViewer.tsx (.env 뷰어)

```tsx
export default function ProjectEnvViewer({ projectId }: { projectId: string }) {
  const [envData, setEnvData] = useState<ProjectEnvResponse | null>(null)
  const [masked, setMasked] = useState(true)
  const [showExample, setShowExample] = useState(false)

  return (
    <div style={envViewerStyle}>
      {/* 툴바 */}
      <Toolbar>
        <Toggle checked={masked} onChange={setMasked} label="🔒 마스킹" />
        {envData?.has_env_example && (
          <Button onClick={() => setShowExample(!showExample)}>
            📄 .env.example {showExample ? '숨기기' : '보기'}
          </Button>
        )}
      </Toolbar>

      {/* .env 내용 */}
      {envData?.has_env ? (
        <EnvTable>
          <thead>
            <tr><th>Key</th><th>Value</th></tr>
          </thead>
          <tbody>
            {Object.entries(envData.env_content).map(([key, value]) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{masked ? maskValue(value) : value}</td>
              </tr>
            ))}
          </tbody>
        </EnvTable>
      ) : (
        <EmptyState message=".env 파일이 없습니다" />
      )}

      {/* .env.example (비교) */}
      {showExample && envData?.env_example_content && (
        <EnvExampleSection>
          <h4>📄 .env.example</h4>
          <EnvTable>
            {Object.entries(envData.env_example_content).map(([key, value]) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{value}</td>
              </tr>
            ))}
          </EnvTable>
        </EnvExampleSection>
      )}
    </div>
  )
}

function maskValue(value: string): string {
  if (value.length <= 4) return '••••'
  return value.slice(0, 2) + '••••' + value.slice(-2)
}
```

---

## 5. 백엔드 서비스

### 5.1 local_scanner.py

```python
"""로컬 워크스페이스 스캔 서비스"""

import os
import configparser
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ScannedRepo:
    name: str
    path: str
    remote_url: str | None
    language: str | None


def scan_directory(scan_path: str, recursive: bool = False) -> list[ScannedRepo]:
    """디렉토리에서 Git 레포 스캔"""
    repos = []
    base = Path(scan_path)

    if not base.exists() or not base.is_dir():
        return repos

    dirs_to_check = [base]
    if recursive:
        dirs_to_check = [d for d in base.rglob("*") if d.is_dir()]
    else:
        dirs_to_check = [d for d in base.iterdir() if d.is_dir()]

    for dir_path in dirs_to_check:
        git_dir = dir_path / ".git"
        if not git_dir.exists():
            continue

        repos.append(ScannedRepo(
            name=dir_path.name,
            path=str(dir_path.absolute()),
            remote_url=extract_git_remote(dir_path),
            language=detect_language(dir_path),
        ))

    return repos


def extract_git_remote(repo_path: Path) -> str | None:
    """Git config에서 origin URL 추출"""
    config_file = repo_path / ".git" / "config"
    if not config_file.exists():
        return None

    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        return config.get('remote "origin"', "url", fallback=None)
    except Exception:
        return None


def detect_language(repo_path: Path) -> str | None:
    """주요 언어 감지"""
    indicators = {
        "Python": ["pyproject.toml", "setup.py", "requirements.txt"],
        "TypeScript": ["tsconfig.json"],
        "JavaScript": ["package.json"],
        "Go": ["go.mod"],
        "Rust": ["Cargo.toml"],
        "Java": ["pom.xml", "build.gradle"],
    }

    for lang, files in indicators.items():
        for f in files:
            if (repo_path / f).exists():
                return lang
    return None


def normalize_github_url(url: str) -> str:
    """GitHub URL 정규화"""
    if not url:
        return ""
    url = url.replace("git@github.com:", "github.com/")
    url = url.replace("https://github.com/", "github.com/")
    url = url.replace("http://github.com/", "github.com/")
    url = url.rstrip(".git")
    return url.lower()
```

### 5.2 project_service.py

```python
"""프로젝트 관리 서비스"""

from uuid import uuid4
from sqlalchemy.orm import Session

from .models import Project, ScanPath, GithubRepo
from .local_scanner import scan_directory, normalize_github_url, ScannedRepo


async def sync_scan_path(scan_path_id: str, db: Session) -> dict:
    """스캔 경로의 프로젝트 동기화"""
    scan_path = db.query(ScanPath).filter(ScanPath.id == scan_path_id).first()
    if not scan_path:
        raise ValueError("Scan path not found")

    # 스캔 실행
    scanned = scan_directory(scan_path.path, scan_path.recursive)

    # GitHub repos 조회 (매칭용)
    github_repos = db.query(GithubRepo).all()
    github_url_map = {
        normalize_github_url(r.clone_url): r for r in github_repos
    }

    created, updated, unchanged = 0, 0, 0

    for repo in scanned:
        existing = db.query(Project).filter(
            Project.local_path == repo.path
        ).first()

        # GitHub 매칭
        github_repo = None
        if repo.remote_url:
            normalized = normalize_github_url(repo.remote_url)
            github_repo = github_url_map.get(normalized)

        if existing:
            # 업데이트 필요 여부 확인
            needs_update = False
            if github_repo and not existing.github_repo_id:
                existing.github_repo_id = github_repo.id
                existing.source_type = "github"
                needs_update = True
            if repo.language and existing.language != repo.language:
                existing.language = repo.language
                needs_update = True

            if needs_update:
                updated += 1
            else:
                unchanged += 1
        else:
            # 새 프로젝트 생성
            project = Project(
                id=uuid4().hex,
                name=repo.name,
                local_path=repo.path,
                scan_path_id=scan_path_id,
                source_type="github" if github_repo else "local",
                github_repo_id=github_repo.id if github_repo else None,
                language=repo.language,
            )
            db.add(project)
            created += 1

    # 스캔 경로 상태 업데이트
    scan_path.last_scanned_at = func.now()
    scan_path.project_count = created + updated + unchanged

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "total": created + updated + unchanged,
    }


def read_project_env(project: Project, masked: bool = True) -> dict:
    """프로젝트의 .env 파일 읽기"""
    if not project.local_path:
        return {"has_env": False, "has_env_example": False}

    from pathlib import Path
    base = Path(project.local_path)

    result = {
        "has_env": False,
        "has_env_example": False,
        "env_content": {},
        "env_example_content": None,
    }

    # .env 읽기
    env_file = base / ".env"
    if env_file.exists():
        result["has_env"] = True
        result["env_content"] = parse_env_file(env_file, masked)

    # .env.example 읽기
    env_example = base / ".env.example"
    if env_example.exists():
        result["has_env_example"] = True
        result["env_example_content"] = parse_env_file(env_example, masked=False)

    return result


def parse_env_file(path: Path, masked: bool = False) -> dict[str, str]:
    """env 파일 파싱"""
    content = {}
    sensitive_keys = {"password", "secret", "key", "token", "api_key", "private"}

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if masked:
            # 민감한 키 마스킹
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_keys):
                value = mask_value(value)

        content[key] = value

    return content


def mask_value(value: str) -> str:
    """값 마스킹"""
    if len(value) <= 4:
        return "••••"
    return value[:2] + "••••" + value[-2:]
```

### 5.3 env_reader.py

```python
"""프로젝트 설정 파일 읽기"""

import json
import tomllib
from pathlib import Path


CONFIG_FILES = [
    ("package.json", "json"),
    ("pyproject.toml", "toml"),
    ("tsconfig.json", "json"),
    ("go.mod", "text"),
    ("Cargo.toml", "toml"),
    (".eslintrc.json", "json"),
    ("docker-compose.yml", "yaml"),
]


def read_project_configs(project_path: str) -> list[dict]:
    """프로젝트 설정 파일들 읽기"""
    base = Path(project_path)
    configs = []

    for filename, filetype in CONFIG_FILES:
        filepath = base / filename
        if not filepath.exists():
            continue

        content = read_config_file(filepath, filetype)
        configs.append({
            "name": filename,
            "path": str(filepath),
            "type": filetype,
            "content": content,
        })

    return configs


def read_config_file(path: Path, filetype: str) -> dict | str:
    """설정 파일 읽기"""
    text = path.read_text()

    if filetype == "json":
        return json.loads(text)
    elif filetype == "toml":
        return tomllib.loads(text)
    else:
        return text
```

---

## 6. 구현 단계

### Phase 1: DB 모델 & 마이그레이션
- [ ] 1.1 `ScanPath` 모델 추가
- [ ] 1.2 `Project` 모델 추가
- [ ] 1.3 `GithubInstallation` 모델 추가
- [ ] 1.4 `GithubRepo` 모델 추가
- [ ] 1.5 DDL 마이그레이션 스크립트 추가 (`main.py`)

### Phase 2: 로컬 스캔 서비스
- [ ] 2.1 `local_scanner.py` 구현
- [ ] 2.2 `project_service.py` 구현
- [ ] 2.3 `env_reader.py` 구현
- [ ] 2.4 단위 테스트 작성

### Phase 3: Scan Paths API
- [ ] 3.1 `scan_paths_router.py` 생성
- [ ] 3.2 CRUD 엔드포인트 구현
- [ ] 3.3 스캔 실행 엔드포인트 구현
- [ ] 3.4 스키마 정의 (`schemas.py`)
- [ ] 3.5 API 테스트 작성

### Phase 4: Projects API
- [ ] 4.1 `projects_router.py` 생성
- [ ] 4.2 목록/상세 엔드포인트 구현
- [ ] 4.3 .env 조회 엔드포인트 구현
- [ ] 4.4 설정파일 조회 엔드포인트 구현
- [ ] 4.5 분석 이력 엔드포인트 구현
- [ ] 4.6 API 테스트 작성

### Phase 5: GitHub 연동 (별도 문서 참조)
- [ ] 5.1 GitHub App 설정
- [ ] 5.2 `github_client.py` 구현
- [ ] 5.3 `github_router.py` 구현
- [ ] 5.4 Webhook 처리
- [ ] 5.5 레포 동기화 서비스

### Phase 6: 프론트엔드 - 사이드바 확장
- [ ] 6.1 사이드바에 Control 메뉴 추가
- [ ] 6.2 2단 사이드바 레이아웃 구현
- [ ] 6.3 `ControlCenter.tsx` 컨테이너
- [ ] 6.4 `ControlSubPanel.tsx` 서브패널

### Phase 7: 프론트엔드 - Sources 관리
- [ ] 7.1 `SourceList.tsx` 구현
- [ ] 7.2 `ScanPathItem.tsx` 구현
- [ ] 7.3 `GitHubInstallItem.tsx` 구현
- [ ] 7.4 `AddScanPathModal.tsx` 구현
- [ ] 7.5 스캔 실행 & 동기화 기능

### Phase 8: 프론트엔드 - Projects 관리
- [ ] 8.1 `ProjectList.tsx` 구현
- [ ] 8.2 `ProjectItem.tsx` 구현
- [ ] 8.3 프로젝트 검색/필터 기능

### Phase 9: 프론트엔드 - Project Detail
- [ ] 9.1 `ProjectDetail.tsx` 메인
- [ ] 9.2 `ProjectOverview.tsx` 탭
- [ ] 9.3 `ProjectEnvViewer.tsx` 탭
- [ ] 9.4 `ProjectConfigViewer.tsx` 탭
- [ ] 9.5 `ProjectHistory.tsx` 탭

### Phase 10: 서비스 연동
- [ ] 10.1 채팅에서 프로젝트 선택 연동
- [ ] 10.2 오케스트레이션 실행 시 프로젝트 사용
- [ ] 10.3 분석 완료 시 이력 저장

---

## 7. 환경 변수

```bash
# 기존
ORA_PROJECTS_ROOT=/workspace/Ora     # 기본 스캔 경로 (선택적)

# GitHub App (새로 추가)
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----..."
GITHUB_WEBHOOK_SECRET=whsec_xxxxx
GITHUB_APP_NAME=ora-automation
```

---

## 8. 보안 고려사항

### 8.1 .env 파일 접근
- 민감한 값 기본 마스킹
- 마스킹 해제는 프론트엔드에서만 (API는 항상 마스킹 옵션)
- 파일 시스템 접근 권한 확인

### 8.2 경로 검증
- `..` 경로 traversal 방지
- 허용된 상위 경로 내에서만 스캔
- 심볼릭 링크 처리 주의

### 8.3 GitHub Webhook
- `X-Hub-Signature-256` 검증 필수
- Installation token 안전하게 관리

---

## 9. 테스트 계획

### 9.1 단위 테스트
- `local_scanner.py` 함수별 테스트
- `project_service.py` 서비스 테스트
- URL 정규화 테스트

### 9.2 API 테스트
- Scan Paths CRUD
- Projects CRUD
- .env 조회 (마스킹 확인)

### 9.3 통합 테스트
- 스캔 → 프로젝트 생성 플로우
- GitHub 동기화 → 매칭 플로우

### 9.4 프론트엔드 테스트
- TypeScript 타입 체크
- 컴포넌트 렌더링 테스트
