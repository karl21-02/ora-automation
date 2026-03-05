"""LLM provider abstraction for multi-provider support."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ModelTier:
    LITE = "lite"    # simple aggregation (gemini-2.0-flash-lite / gpt-4o-mini / haiku)
    FLASH = "flash"  # scoring, QA (gemini-2.5-flash / gpt-4o / sonnet)
    PRO = "pro"      # complex reasoning (gemini-2.5-pro / o3 / opus)


# Task -> Tier auto-mapping (based on payload["version"])
TASK_TIER_MAP: dict[str, str] = {
    # Pro: complex reasoning, long narrative
    "llm-topic-discovery-v1": ModelTier.PRO,
    "llm-deliberation-v1": ModelTier.PRO,
    "llm-consensus-v2": ModelTier.PRO,
    "llm-strategy-v1": ModelTier.PRO,
    "llm-executive-summary-v1": ModelTier.PRO,
    "llm-asis-analysis-v1": ModelTier.PRO,
    "llm-tobe-direction-v1": ModelTier.PRO,
    "llm-feasibility-evidence-v1": ModelTier.PRO,
    "llm-fallback-decisions-v1": ModelTier.PRO,
    # Flash: scoring, QA verification
    "llm-scoring-v1": ModelTier.FLASH,
    "llm-qa-v1": ModelTier.FLASH,
    # Lite: simple aggregation
    "llm-phase-plan-v1": ModelTier.LITE,
    "llm-consensus-rank-v1": ModelTier.LITE,
}

TIER_DEFAULT_TIMEOUTS: dict[str, float] = {
    ModelTier.LITE: 30.0,
    ModelTier.FLASH: 60.0,
    ModelTier.PRO: 120.0,
}


def resolve_tier(payload: dict) -> str:
    """Resolve the model tier for a given payload based on its version field."""
    return TASK_TIER_MAP.get(payload.get("version", ""), ModelTier.FLASH)


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations: GeminiProvider, (future) OpenAIProvider, AnthropicProvider
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider's credentials/config are present."""

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_content: str,
        tier: str = ModelTier.FLASH,
        timeout: float | None = None,
        temperature: float | None = None,
    ) -> str:
        """Call the LLM and return raw text response. Raises on failure."""

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'Gemini Vertex AI')."""
