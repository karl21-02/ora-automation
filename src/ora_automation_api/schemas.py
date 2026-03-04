from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class OrchestrationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idempotency_key: str | None
    user_prompt: str
    target: str
    agent_role: str
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
