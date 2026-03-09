"""Shared utility functions for orchestrator modules."""
from __future__ import annotations


def agent_score_key(agent: str) -> str:
    """Generate a normalized score key for an agent.

    Converts agent name to lowercase and replaces spaces with underscores.
    """
    return agent.lower().replace(" ", "_")


def clamp_score(value: float, lo: float = 0.0, hi: float = 10.0, decimals: int = 2) -> float:
    """Clamp a score value to [lo, hi] range with rounding.

    Args:
        value: The score value to clamp
        lo: Minimum allowed value (default: 0.0)
        hi: Maximum allowed value (default: 10.0)
        decimals: Number of decimal places to round to (default: 2)

    Returns:
        Clamped and rounded score value
    """
    return max(lo, min(hi, round(value, decimals)))
