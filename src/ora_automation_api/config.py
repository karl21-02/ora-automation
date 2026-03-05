from __future__ import annotations

import os
from pathlib import Path


DEFAULT_ALLOWED_TARGETS = (
    "run",
    "run-direct",
    "run-cycle",
    "run-loop",
    "run-cycle-deep",
    "run-single",
    "e2e-service",
    "e2e-service-all",
    "qa-program",
    "qa-program-loop",
    "verify-sources",
)

DEFAULT_AGENT_ROLES = (
    "ceo",
    "pm",
    "researcher",
    "engineer",
    "qa",
)


def _parse_csv(value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = [item.strip() for item in value.split(",") if item.strip()]
    if not raw:
        return default
    deduped: list[str] = []
    for item in raw:
        if item not in deduped:
            deduped.append(item)
    return tuple(deduped)


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://ora:ora@db:5432/ora_automation",
        )
        self.automation_root = Path(
            os.getenv("ORA_AUTOMATION_ROOT", "/workspace/Ora/ora-automation")
        ).resolve()
        self.run_output_dir = Path(
            os.getenv(
                "ORA_AUTOMATION_RUN_OUTPUT",
                str(self.automation_root / "research_reports" / "api_runs"),
            )
        ).resolve()
        self.allowed_targets = _parse_csv(
            os.getenv("ORA_AUTOMATION_ALLOWED_TARGETS", ",".join(DEFAULT_ALLOWED_TARGETS)),
            DEFAULT_ALLOWED_TARGETS,
        )
        self.default_target = os.getenv("ORA_AUTOMATION_DEFAULT_TARGET", "run-cycle").strip()
        self.default_timeout_seconds = float(
            os.getenv("ORA_AUTOMATION_COMMAND_TIMEOUT", "3600").strip()
        )

        self.agent_roles = _parse_csv(
            os.getenv("ORA_AUTOMATION_AGENT_ROLES", ",".join(DEFAULT_AGENT_ROLES)),
            DEFAULT_AGENT_ROLES,
        )
        self.default_max_attempts = int(os.getenv("ORA_AUTOMATION_MAX_ATTEMPTS", "3").strip())
        self.heartbeat_interval_seconds = float(
            os.getenv("ORA_AUTOMATION_HEARTBEAT_INTERVAL_SECONDS", "2.0").strip()
        )
        self.stale_timeout_seconds = float(
            os.getenv("ORA_AUTOMATION_STALE_TIMEOUT_SECONDS", "120.0").strip()
        )
        self.retry_base_seconds = float(
            os.getenv("ORA_AUTOMATION_RETRY_BASE_SECONDS", "15.0").strip()
        )
        self.retry_max_seconds = float(
            os.getenv("ORA_AUTOMATION_RETRY_MAX_SECONDS", "600.0").strip()
        )
        self.projects_root = Path(
            os.getenv("ORA_PROJECTS_ROOT", str(self.automation_root.parent))
        ).resolve()

        self.assistant_name = os.getenv("ORA_ASSISTANT_NAME", "Ora").strip()

        self.llm_planner_cmd = os.getenv("ORA_AUTOMATION_LLM_PLANNER_CMD", "").strip()
        self.llm_planner_timeout_seconds = float(
            os.getenv("ORA_AUTOMATION_LLM_PLANNER_TIMEOUT_SECONDS", "30.0").strip()
        )

        self.rabbitmq_url = os.getenv(
            "RABBITMQ_URL",
            "amqp://guest:guest@rabbitmq:5672/%2F",
        ).strip()
        self.rabbitmq_exchange = os.getenv(
            "RABBITMQ_EXCHANGE",
            "ora.automation",
        ).strip()
        self.rabbitmq_retry_exchange = os.getenv(
            "RABBITMQ_RETRY_EXCHANGE",
            "ora.automation.retry",
        ).strip()
        self.rabbitmq_dlx_exchange = os.getenv(
            "RABBITMQ_DLX_EXCHANGE",
            "ora.automation.dlx",
        ).strip()
        self.rabbitmq_queue_prefix = os.getenv(
            "RABBITMQ_QUEUE_PREFIX",
            "ora.automation.agent",
        ).strip()
        self.rabbitmq_prefetch = int(os.getenv("RABBITMQ_PREFETCH", "1").strip())
        self.rabbitmq_reconnect_seconds = float(
            os.getenv("RABBITMQ_RECONNECT_SECONDS", "2.0").strip()
        )

        # Notion integration
        self.notion_api_token = os.getenv("NOTION_API_TOKEN", "").strip()
        self.notion_api_version = os.getenv("NOTION_API_VERSION", "2022-06-28").strip()
        self.notion_auto_publish = os.getenv("NOTION_AUTO_PUBLISH", "0").strip() in (
            "1",
            "true",
            "yes",
        )

        # Scheduler
        self.scheduler_enabled = os.getenv("ORA_SCHEDULER_ENABLED", "0").strip() in (
            "1",
            "true",
            "yes",
        )
        self.scheduler_poll_seconds = int(
            os.getenv("ORA_SCHEDULER_POLL_SECONDS", "60").strip()
        )


settings = Settings()
