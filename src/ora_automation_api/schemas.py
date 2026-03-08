from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectInfo(BaseModel):
    name: str
    path: str
    has_makefile: bool = False
    has_dockerfile: bool = False
    description: str = ""


class DecisionCreate(BaseModel):
    decision_id: str | None = None
    owner: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1, max_length=8000)
    risk: str = Field(..., min_length=1, max_length=8000)
    next_action: str = Field(..., min_length=1, max_length=8000)
    due: datetime | None = None
    payload: dict = Field(default_factory=dict)


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str | None
    owner: str
    rationale: str
    risk: str
    next_action: str
    due: datetime | None
    payload: dict
    created_at: datetime


class OrchestrationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    stage: str
    event_type: str
    message: str
    payload: dict
    created_at: datetime


class OrchestrationRunCreate(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=4000)
    target: str | None = Field(default=None)
    env: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = False
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=86400.0)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    agent_role: str | None = Field(default=None, min_length=1, max_length=32)
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    pipeline_stages: list[str] = Field(
        default_factory=lambda: ["analysis", "deliberation", "execution"]
    )
    execution_command: str | None = Field(default=None, min_length=1, max_length=4096)
    rollback_command: str | None = Field(default=None, min_length=1, max_length=4096)
    decision: DecisionCreate | None = None
    org_id: str | None = Field(default=None, min_length=1, max_length=36)
    guest_agent_ids: list[str] = Field(
        default_factory=list,
        description="Guest agents from other orgs. Format: 'org_id:agent_id'",
    )


class OrchestrationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idempotency_key: str | None
    user_prompt: str
    target: str
    agent_role: str
    org_id: str | None = None
    command: str
    rollback_command: str | None
    env: dict
    pipeline_stages: list
    current_stage: str | None
    status: str
    fail_label: str
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    pause_requested: bool
    cancel_requested: bool
    guest_agent_ids: list[str] = Field(default_factory=list)
    locked_by: str | None
    locked_at: datetime | None
    heartbeat_at: datetime | None
    decision_id: str | None
    exit_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class OrchestrationRunList(BaseModel):
    items: list[OrchestrationRunRead]
    total: int


class RunActionResponse(BaseModel):
    run_id: str
    status: str
    pause_requested: bool
    cancel_requested: bool


class LlmPlanRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    context: dict = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=300.0)


class LlmPlanResponse(BaseModel):
    target: str
    agent_role: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    max_attempts: int | None = None
    pipeline_stages: list[str] = Field(default_factory=lambda: ["analysis", "deliberation", "execution"])
    execution_command: str | None = None
    rollback_command: str | None = None
    decision: dict | None = None
    planner_metadata: dict = Field(default_factory=dict)


class LlmPlanRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    context: dict = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=300.0)
    dry_run: bool = False
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    env_overrides: dict[str, str] = Field(default_factory=dict)


# ── Chat (chatbot frontend) ──────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)
    org_id: str | None = Field(default=None, max_length=36)


class ChatPlan(BaseModel):
    target: str
    env: dict[str, str] = Field(default_factory=dict)
    label: str = ""


class ChatChoice(BaseModel):
    label: str
    description: str = ""
    value: str


class OrgRecommendOption(BaseModel):
    org_id: str
    org_name: str
    description: str = ""
    score: float = 0.0
    reason: str = ""
    is_recommended: bool = False


class ChatResponse(BaseModel):
    reply: str
    plan: ChatPlan | None = None
    plans: list[ChatPlan] | None = None
    choices: list[ChatChoice] | None = None
    project_select: list[ProjectInfo] | None = None
    org_recommend: list[OrgRecommendOption] | None = None
    run_id: str | None = None
    dialog_state: str | None = None
    confirmation_required: bool = False
    intent_summary: str | None = None


class BatchRunCreate(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=4000)
    plans: list[ChatPlan]
    org_id: str | None = Field(default=None, max_length=36)


class BatchRunResponse(BaseModel):
    runs: list[OrchestrationRunRead]


class ReportListItem(BaseModel):
    filename: str
    created_at: datetime
    size_bytes: int
    report_type: str  # "markdown" | "json"


# ── Conversations (DB-backed) ────────────────────────────────────────


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: str
    role: str
    content: str
    plan: dict | None = None
    run_id: str | None = None
    created_at: datetime


class ConversationRead(BaseModel):
    id: str
    title: str
    org_id: str | None = None
    org_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[ChatMessageRead] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    id: str | None = None
    title: str = ""
    org_id: str | None = Field(default=None, max_length=36)


class ConversationUpdate(BaseModel):
    title: str | None = None
    org_id: str | None = None  # empty string = unbind


class ConversationList(BaseModel):
    items: list[ConversationRead]
    total: int


# ── Notion Integration ─────────────────────────────────────────────


class NotionSetupResponse(BaseModel):
    hub_page_id: str
    reports_db_id: str
    topics_db_id: str
    dashboard_page_id: str
    status: str = "created"


class NotionPublishResponse(BaseModel):
    report_page_id: str
    report_url: str | None = None
    topic_pages: list[dict] = Field(default_factory=list)
    status: str = "published"


class NotionStatusResponse(BaseModel):
    connected: bool
    bot_name: str | None = None
    synced_reports_count: int = 0
    unsynced_reports: list[str] = Field(default_factory=list)
    last_sync_at: datetime | None = None


class NotionSyncResponse(BaseModel):
    synced: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    status: str = "completed"


# ── Scheduler ──────────────────────────────────────────────────────


class ScheduledJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    target: str = Field(default="run-cycle")
    env: dict[str, str] = Field(default_factory=dict)
    interval_minutes: int | None = None
    cron_expression: str | None = None
    enabled: bool = True
    auto_publish_notion: bool = False


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target: str | None = None
    env: dict[str, str] | None = None
    interval_minutes: int | None = Field(default=None)
    cron_expression: str | None = Field(default=None)
    enabled: bool | None = None
    auto_publish_notion: bool | None = None


class ScheduledJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    target: str
    env: dict
    interval_minutes: int | None = None
    cron_expression: str | None = None
    enabled: bool
    auto_publish_notion: bool
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_run_id: str | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Organizations ─────────────────────────────────────────────────


class OrgAgentCreate(BaseModel):
    agent_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
        description="Unique agent identifier: letters, digits, underscore. Must start with letter.",
    )
    display_name: str = Field(..., min_length=1, max_length=128)
    display_name_ko: str = Field(default="", max_length=256)
    role: str = Field(default="", max_length=32)
    tier: int = Field(default=1, ge=1, le=4)
    domain: str | None = Field(default=None, max_length=64)
    team: str = Field(default="", max_length=64)
    silo_id: str | None = Field(default=None, max_length=36)
    chapter_id: str | None = Field(default=None, max_length=36)
    is_clevel: bool = False
    weight_score: float = Field(default=1.0, ge=0.0, le=10.0)
    personality: dict = Field(default_factory=dict)
    behavioral_directives: list = Field(default_factory=list)
    constraints: list = Field(default_factory=list)
    decision_focus: list = Field(default_factory=list)
    weights: dict = Field(default_factory=dict)
    trust_map: dict = Field(default_factory=dict)
    system_prompt_template: str = Field(default="", max_length=4000)
    enabled: bool = True
    sort_order: int = 0


class OrgAgentUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    display_name_ko: str | None = Field(default=None, max_length=256)
    role: str | None = Field(default=None, max_length=32)
    tier: int | None = Field(default=None, ge=1, le=4)
    domain: str | None = None
    team: str | None = Field(default=None, max_length=64)
    silo_id: str | None = None
    chapter_id: str | None = None
    is_clevel: bool | None = None
    weight_score: float | None = Field(default=None, ge=0.0, le=10.0)
    personality: dict | None = None
    behavioral_directives: list | None = None
    constraints: list | None = None
    decision_focus: list | None = None
    weights: dict | None = None
    trust_map: dict | None = None
    system_prompt_template: str | None = Field(default=None, max_length=4000)
    enabled: bool | None = None
    sort_order: int | None = None


class OrgAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    agent_id: str
    silo_id: str | None = None
    chapter_id: str | None = None
    is_clevel: bool
    weight_score: float
    display_name: str
    display_name_ko: str
    role: str
    tier: int
    domain: str | None
    team: str
    personality: dict
    behavioral_directives: list
    constraints: list
    decision_focus: list
    weights: dict
    trust_map: dict
    system_prompt_template: str | None
    enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    teams: dict = Field(default_factory=dict)
    flat_mode_agents: list[str] = Field(default_factory=list)
    agent_final_weights: dict[str, float] = Field(default_factory=dict)
    pipeline_params: dict = Field(default_factory=dict)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    teams: dict | None = None
    flat_mode_agents: list[str] | None = None
    agent_final_weights: dict[str, float] | None = None
    pipeline_params: dict | None = None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    is_preset: bool
    teams: dict
    flat_mode_agents: list
    agent_final_weights: dict
    pipeline_params: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class OrganizationDetail(OrganizationRead):
    agents: list[OrgAgentRead] = Field(default_factory=list)
    silos: list["OrgSiloRead"] = Field(default_factory=list)
    chapters: list["OrgChapterRead"] = Field(default_factory=list)


class OrganizationList(BaseModel):
    items: list[OrganizationRead]
    total: int


# ── Silos & Chapters ─────────────────────────────────────────────


class OrgSiloCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    color: str = Field(default="#3b82f6", max_length=7)
    sort_order: int = 0


class OrgSiloUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    color: str | None = Field(default=None, max_length=7)
    sort_order: int | None = None


class OrgSiloRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    description: str | None
    color: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class OrgChapterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    shared_directives: list = Field(default_factory=list)
    shared_constraints: list = Field(default_factory=list)
    shared_decision_focus: list = Field(default_factory=list)
    chapter_prompt: str = Field(default="", max_length=2000)
    color: str = Field(default="#8b5cf6", max_length=7)
    icon: str = Field(default="📁", max_length=4)
    sort_order: int = 0


class OrgChapterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    shared_directives: list | None = None
    shared_constraints: list | None = None
    shared_decision_focus: list | None = None
    chapter_prompt: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, max_length=7)
    icon: str | None = Field(default=None, max_length=4)
    sort_order: int | None = None


class OrgChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    description: str | None
    shared_directives: list
    shared_constraints: list
    shared_decision_focus: list
    chapter_prompt: str
    color: str
    icon: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
