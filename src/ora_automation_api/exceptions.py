"""Custom exception classes for ora-automation API.

Exception Hierarchy:
    OraAutomationError (base)
    ├── LLMError
    │   ├── LLMTimeoutError
    │   ├── LLMParseError
    │   └── LLMConnectionError
    ├── OrchestrationError
    │   ├── PipelineError
    │   └── QueueError
    ├── DialogError
    │   ├── IntentParseError
    │   └── SlotValidationError
    └── NotionError
        ├── NotionAPIError (already exists in notion_client.py)
        └── NotionPublishError

Usage:
    from .exceptions import LLMError, LLMTimeoutError

    try:
        result = call_llm(...)
    except LLMTimeoutError as e:
        logger.warning("LLM timed out: %s", e)
    except LLMError as e:
        logger.error("LLM failed: %s", e)
"""
from __future__ import annotations


class OraAutomationError(Exception):
    """Base exception for all ora-automation errors."""

    def __init__(self, message: str = "", details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── LLM Errors ─────────────────────────────────────────────────────────


class LLMError(OraAutomationError):
    """Base exception for LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """LLM call timed out."""
    pass


class LLMParseError(LLMError):
    """Failed to parse LLM response (invalid JSON, etc.)."""
    pass


class LLMConnectionError(LLMError):
    """Failed to connect to LLM service."""
    pass


# ── Orchestration Errors ───────────────────────────────────────────────


class OrchestrationError(OraAutomationError):
    """Base exception for orchestration/pipeline errors."""
    pass


class PipelineError(OrchestrationError):
    """Pipeline execution failed."""
    pass


class QueueError(OrchestrationError):
    """Message queue (RabbitMQ) operation failed."""
    pass


# ── Dialog Errors ──────────────────────────────────────────────────────


class DialogError(OraAutomationError):
    """Base exception for dialog/UPCE engine errors."""
    pass


class IntentParseError(DialogError):
    """Failed to parse user intent from LLM response."""
    pass


class SlotValidationError(DialogError):
    """Slot validation failed (invalid cron expression, etc.)."""
    pass


# ── Notion Errors ──────────────────────────────────────────────────────


class NotionError(OraAutomationError):
    """Base exception for Notion integration errors."""
    pass


class NotionPublishError(NotionError):
    """Failed to publish content to Notion."""
    pass
