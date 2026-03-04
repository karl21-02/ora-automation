"""LLM-based agent scoring for R&D topics.

All scoring is performed via LLM calls. No hardcoded rules or formulas.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .config import LLM_SCORING_CMD_ENV
from .llm_client import run_llm_command
from .types import AgentPersona, LLMResult, TopicState

logger = logging.getLogger(__name__)


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, round(value, 2)))


_SCORING_SYSTEM_PROMPT = """\
당신은 R&D 연구 주제 평가 에이전트입니다.

## 페르소나
{persona_prompt}

## 평가 기준
각 토픽에 대해 아래 5가지 차원으로 0-10 점수를 매기세요:
- impact: 사업적 영향력 (시장성, 수주 잠재력, 고객 가치)
- feasibility: 구현 가능성 (코드 자산, 인력, 기간)
- novelty: 기술적 신규성 (학술적 기여, 차별화)
- research_signal: 연구 근거 강도 (논문, 학회, 데이터)
- risk_penalty: 리스크 수준 (보안, 운영, 회귀 위험)

## 출력 형식
반드시 아래 JSON 스키마를 따르세요:
{{
  "scores": {{
    "<topic_id>": {{
      "impact": 0-10,
      "feasibility": 0-10,
      "novelty": 0-10,
      "research_signal": 0-10,
      "risk_penalty": 0-10,
      "support": true/false,
      "challenge": true/false,
      "rationale": "이유 (1-2문장)"
    }}
  }}
}}
"""


def _build_scoring_payload(
    persona: AgentPersona,
    topic_states: dict[str, TopicState],
) -> dict[str, Any]:
    topics_data: dict[str, Any] = {}
    for topic_id, state in topic_states.items():
        topics_data[topic_id] = {
            "topic_name": state.topic_name,
            "keyword_hits": state.keyword_hits,
            "business_hits": state.business_hits,
            "novelty_hits": state.novelty_hits,
            "code_hits": state.code_hits,
            "doc_hits": state.doc_hits,
            "history_hits": state.history_hits,
            "project_count": state.project_count,
            "evidence_sample": [
                {"file": e.file, "snippet": e.snippet}
                for e in state.evidence[:4]
            ],
        }

    return {
        "version": "llm-scoring-v1",
        "agent_id": persona.agent_id,
        "agent_role": persona.role,
        "agent_tier": persona.tier,
        "agent_weights": dict(persona.weights),
        "topics": topics_data,
    }


def _parse_scoring_result(
    result: LLMResult,
    topic_ids: list[str],
) -> dict[str, dict[str, float]]:
    if result.status != "ok":
        return {}

    scores_raw = result.parsed.get("scores", {})
    if not isinstance(scores_raw, dict):
        return {}

    parsed: dict[str, dict[str, float]] = {}
    for topic_id in topic_ids:
        item = scores_raw.get(topic_id)
        if not isinstance(item, dict):
            continue
        features: dict[str, float] = {}
        for key in ("impact", "feasibility", "novelty", "research_signal", "risk_penalty"):
            try:
                features[key] = _clamp(float(item.get(key, 5.0)))
            except (TypeError, ValueError):
                features[key] = 5.0
        features["support"] = 1.0 if item.get("support") else 0.0
        features["challenge"] = 1.0 if item.get("challenge") else 0.0
        parsed[topic_id] = features

    return parsed


def score_topics_for_agent(
    agent_id: str,
    topic_states: dict[str, TopicState],
    persona: AgentPersona,
    llm_command: str,
    llm_timeout: float = 10.0,
) -> dict[str, dict[str, float]]:
    """Score all topics for a single agent via LLM."""
    system_prompt = _SCORING_SYSTEM_PROMPT.format(
        persona_prompt=persona.system_prompt[:2000],
    )
    payload = _build_scoring_payload(persona, topic_states)
    result = run_llm_command(
        payload=payload,
        command=llm_command,
        timeout=llm_timeout,
        system_prompt=system_prompt,
    )
    parsed = _parse_scoring_result(result, list(topic_states.keys()))
    if not parsed:
        raise RuntimeError(
            f"LLM scoring failed for agent {agent_id}: {result.status} - "
            f"{result.parsed.get('reason', 'unknown')}"
        )
    logger.info("LLM scored %d topics for agent %s", len(parsed), agent_id)
    return parsed


def compute_agent_score(
    features: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute a weighted agent score from LLM-provided features and weight profile."""
    total = 0.0
    for key, weight in weights.items():
        if key == "risk":
            val = features.get("risk_penalty", 5.0)
        else:
            val = features.get(key, 5.0)
        try:
            total += weight * float(val)
        except (TypeError, ValueError):
            total += weight * 5.0
    return _clamp(total)


def score_all_agents(
    topic_states: dict[str, TopicState],
    personas: dict[str, AgentPersona],
    llm_command: str,
    llm_timeout: float = 10.0,
    agent_definitions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """Score all topics for all agents via LLM.

    Returns ``{agent_id: {topic_id: {feature: value, ...}}}``
    """
    all_scores: dict[str, dict[str, dict[str, float]]] = {}

    for agent_id, persona in personas.items():
        scores = score_topics_for_agent(
            agent_id=agent_id,
            topic_states=topic_states,
            persona=persona,
            llm_command=llm_command,
            llm_timeout=llm_timeout,
        )
        all_scores[agent_id] = scores

    return all_scores
