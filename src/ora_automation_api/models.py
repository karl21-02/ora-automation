from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    """사용자 테이블 - Google OAuth로 인증된 사용자."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    picture: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrchestrationRun(Base):
    __tablename__ = "orchestration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(32), nullable=False, default="engineer")
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    command: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    env: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pipeline_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    current_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    guest_agent_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    fail_label: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("orchestration_decisions.id"),
        nullable=True,
        index=True,
    )
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrchestrationDecision(Base):
    __tablename__ = "orchestration_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("orchestration_runs.id"),
        nullable=True,
        index=True,
    )
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dialog_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dialog_context_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class OrchestrationEvent(Base):
    __tablename__ = "orchestration_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orchestration_runs.id"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class NotionSyncState(Base):
    __tablename__ = "notion_sync_state"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_key", name="uq_notion_sync_entity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(256), nullable=False)
    notion_page_id: Mapped[str] = mapped_column(String(36), nullable=False)
    notion_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    teams: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    flat_mode_agents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    agent_final_weights: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pipeline_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrganizationSilo(Base):
    __tablename__ = "organization_silos"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_silo_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#3b82f6")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrganizationChapter(Base):
    __tablename__ = "organization_chapters"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_chapter_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_directives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    shared_constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    shared_decision_focus: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    chapter_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#8b5cf6")
    icon: Mapped[str] = mapped_column(String(4), nullable=False, default="📁")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrganizationAgent(Base):
    __tablename__ = "organization_agents"
    __table_args__ = (
        UniqueConstraint("org_id", "agent_id", name="uq_org_agent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    silo_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organization_silos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chapter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organization_chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_clevel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name_ko: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    team: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    personality: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    behavioral_directives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    decision_focus: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weights: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trust_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    system_prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str] = mapped_column(String(64), nullable=False, default="run-cycle")
    env: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cron_expression: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_publish_notion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# =============================================================================
# Project Source Management Models
# =============================================================================


class ScanPath(Base):
    """사용자가 등록한 로컬 스캔 경로.

    프로젝트를 자동으로 감지할 디렉토리 경로를 관리합니다.
    """

    __tablename__ = "scan_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 별칭: "회사", "개인"

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recursive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# =============================================================================
# GitHub App Integration Models
# =============================================================================


class GithubInstallation(Base):
    """GitHub App이 설치된 Organization 또는 User 정보."""

    __tablename__ = "github_installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    installation_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "Organization" or "User"
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)  # org name or username
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Status: active, suspended, deleted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GithubRepo(Base):
    """동기화된 GitHub Repository."""

    __tablename__ = "github_repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    installation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("github_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # GitHub repo info
    repo_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)  # owner/repo
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_url: Mapped[str] = mapped_column(String(500), nullable=False)
    clone_url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")

    # Metadata
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Project(Base):
    """통합 프로젝트 테이블 - 모든 분석 대상의 단일 소스.

    source_type:
      - "local": 로컬 워크스페이스에만 존재
      - "github": GitHub + 로컬이 연결됨
      - "github_only": GitHub만 (clone 필요)
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source type: "local", "github", "github_only"
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="local")

    # Local path (if available)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True)

    # Scan path connection (if created via scan)
    scan_path_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scan_paths.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # GitHub connection (if synced)
    github_repo_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("github_repos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Analysis settings
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Metadata (cached from GitHub or local scan)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

