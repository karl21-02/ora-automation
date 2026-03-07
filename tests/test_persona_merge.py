"""Tests for chapter→agent merging, from_org_config, and auto-derive flat_mode_agents/weights."""
from __future__ import annotations

import pytest

from ora_rd_orchestrator.personas import (
    PersonaRegistry,
    _merge_chapter_into_agent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _agent(
    agent_id: str = "TestAgent",
    *,
    enabled: bool = True,
    chapter_id: str | None = None,
    silo_id: str | None = None,
    weight_score: float = 1.0,
    behavioral_directives: list[str] | None = None,
    constraints: list[str] | None = None,
    decision_focus: list[str] | None = None,
    system_prompt_template: str = "",
) -> dict:
    return {
        "agent_id": agent_id,
        "display_name": agent_id,
        "display_name_ko": agent_id,
        "role": "tester",
        "tier": 2,
        "team": "qa",
        "domain": None,
        "personality": {},
        "weights": {"impact": 0.5},
        "trust_map": {},
        "behavioral_directives": behavioral_directives or [],
        "constraints": constraints or [],
        "decision_focus": decision_focus or [],
        "system_prompt_template": system_prompt_template,
        "enabled": enabled,
        "silo_id": silo_id,
        "chapter_id": chapter_id,
        "is_clevel": False,
        "weight_score": weight_score,
    }


def _chapter(
    chapter_id: str = "ch-1",
    *,
    shared_directives: list[str] | None = None,
    shared_constraints: list[str] | None = None,
    shared_decision_focus: list[str] | None = None,
    chapter_prompt: str = "",
) -> dict:
    return {
        "id": chapter_id,
        "name": "TestChapter",
        "shared_directives": shared_directives or [],
        "shared_constraints": shared_constraints or [],
        "shared_decision_focus": shared_decision_focus or [],
        "chapter_prompt": chapter_prompt,
    }


# ---------------------------------------------------------------------------
# TestMergeChapterIntoAgent
# ---------------------------------------------------------------------------

class TestMergeChapterIntoAgent:
    def test_merge_adds_chapter_directives(self):
        agent = _agent(behavioral_directives=["agent_d1"])
        chapter = _chapter(shared_directives=["ch_d1", "ch_d2"])

        merged = _merge_chapter_into_agent(agent, chapter)

        assert merged["behavioral_directives"] == ["ch_d1", "ch_d2", "agent_d1"]
        # original not mutated
        assert agent["behavioral_directives"] == ["agent_d1"]

    def test_merge_adds_chapter_constraints(self):
        agent = _agent(constraints=["agent_c"])
        chapter = _chapter(shared_constraints=["ch_c"])

        merged = _merge_chapter_into_agent(agent, chapter)

        assert merged["constraints"] == ["ch_c", "agent_c"]

    def test_merge_adds_chapter_decision_focus(self):
        agent = _agent(decision_focus=["quality"])
        chapter = _chapter(shared_decision_focus=["impact"])

        merged = _merge_chapter_into_agent(agent, chapter)

        assert merged["decision_focus"] == ["impact", "quality"]

    def test_merge_prepends_chapter_prompt(self):
        agent = _agent(system_prompt_template="You are an agent.")
        chapter = _chapter(chapter_prompt="Chapter context here.")

        merged = _merge_chapter_into_agent(agent, chapter)

        assert merged["system_prompt_template"].startswith("Chapter context here.")
        assert "You are an agent." in merged["system_prompt_template"]

    def test_merge_no_chapter_prompt_no_change(self):
        agent = _agent(system_prompt_template="Original prompt.")
        chapter = _chapter(chapter_prompt="")

        merged = _merge_chapter_into_agent(agent, chapter)

        assert merged["system_prompt_template"] == "Original prompt."

    def test_merge_chapter_prompt_only(self):
        agent = _agent(system_prompt_template="")
        chapter = _chapter(chapter_prompt="Only chapter prompt.")

        merged = _merge_chapter_into_agent(agent, chapter)

        assert merged["system_prompt_template"] == "Only chapter prompt."


# ---------------------------------------------------------------------------
# TestPersonaRegistryFromOrgConfig
# ---------------------------------------------------------------------------

class TestPersonaRegistryFromOrgConfig:
    def test_from_org_config_basic(self):
        chapter = _chapter(chapter_id="ch-1", shared_directives=["be fair"])
        agents = [
            _agent("A1", chapter_id="ch-1"),
            _agent("A2", chapter_id="ch-1"),
        ]
        org_config = {"agents": agents, "chapters": [chapter]}

        registry = PersonaRegistry.from_org_config(org_config)

        assert len(registry) == 2
        assert "A1" in registry
        assert "A2" in registry

    def test_from_org_config_chapter_prompt_in_system_prompt(self):
        chapter = _chapter(
            chapter_id="ch-1",
            chapter_prompt="You belong to TestChapter.",
        )
        agents = [
            _agent("A1", chapter_id="ch-1", system_prompt_template="Base prompt."),
        ]
        org_config = {"agents": agents, "chapters": [chapter]}

        registry = PersonaRegistry.from_org_config(org_config)
        persona = registry.get_persona("A1")

        assert persona is not None
        assert "You belong to TestChapter." in persona.system_prompt

    def test_from_org_config_chapter_directives_merged(self):
        chapter = _chapter(
            chapter_id="ch-1",
            shared_directives=["ch_directive"],
        )
        agents = [
            _agent("A1", chapter_id="ch-1", behavioral_directives=["agent_directive"]),
        ]
        org_config = {"agents": agents, "chapters": [chapter]}

        registry = PersonaRegistry.from_org_config(org_config)
        persona = registry.get_persona("A1")

        assert persona is not None
        assert "ch_directive" in persona.behavioral_directives
        assert "agent_directive" in persona.behavioral_directives
        assert persona.behavioral_directives.index("ch_directive") < persona.behavioral_directives.index("agent_directive")

    def test_from_org_config_disabled_agent_excluded(self):
        chapter = _chapter(chapter_id="ch-1")
        agents = [
            _agent("A1", chapter_id="ch-1", enabled=True),
            _agent("A2", chapter_id="ch-1", enabled=False),
        ]
        org_config = {"agents": agents, "chapters": [chapter]}

        registry = PersonaRegistry.from_org_config(org_config)

        assert len(registry) == 1
        assert "A1" in registry
        assert "A2" not in registry

    def test_from_org_config_no_chapter_id_no_merge(self):
        chapter = _chapter(chapter_id="ch-1", shared_directives=["should_not_appear"])
        agents = [
            _agent("A1", chapter_id=None, behavioral_directives=["only_agent"]),
        ]
        org_config = {"agents": agents, "chapters": [chapter]}

        registry = PersonaRegistry.from_org_config(org_config)
        persona = registry.get_persona("A1")

        assert persona is not None
        assert "should_not_appear" not in persona.behavioral_directives
        assert "only_agent" in persona.behavioral_directives

    def test_from_org_config_empty_chapters_still_works(self):
        agents = [
            _agent("A1"),
            _agent("A2"),
        ]
        org_config = {"agents": agents, "chapters": []}

        registry = PersonaRegistry.from_org_config(org_config)

        assert len(registry) == 2


# ---------------------------------------------------------------------------
# TestAutoDeriveFlatAgentsAndWeights
# ---------------------------------------------------------------------------

class TestAutoDeriveFlatAgentsAndWeights:
    """pipeline.py의 자동 도출 로직을 단위 테스트 (로직 추출)."""

    @staticmethod
    def _derive_flat_agents(org_config: dict) -> set[str]:
        explicit_flat = org_config.get("flat_mode_agents") or []
        if explicit_flat:
            return set(explicit_flat)
        return {
            a["agent_id"] for a in org_config["agents"]
            if a.get("enabled", True)
        }

    @staticmethod
    def _derive_weights(org_config: dict) -> dict[str, float]:
        explicit_weights = org_config.get("agent_final_weights") or {}
        if explicit_weights:
            return explicit_weights
        return {
            a["agent_id"]: a.get("weight_score", 1.0)
            for a in org_config["agents"]
            if a.get("enabled", True)
        }

    def test_auto_flat_agents_from_enabled(self):
        org_config = {
            "agents": [
                _agent("A1", enabled=True),
                _agent("A2", enabled=True),
                _agent("A3", enabled=False),
            ],
            "flat_mode_agents": [],
            "agent_final_weights": {},
        }
        result = self._derive_flat_agents(org_config)
        assert result == {"A1", "A2"}

    def test_auto_weights_from_weight_score(self):
        org_config = {
            "agents": [
                _agent("A1", weight_score=1.5, enabled=True),
                _agent("A2", weight_score=0.8, enabled=True),
                _agent("A3", weight_score=2.0, enabled=False),
            ],
            "flat_mode_agents": [],
            "agent_final_weights": {},
        }
        result = self._derive_weights(org_config)
        assert result == {"A1": 1.5, "A2": 0.8}

    def test_explicit_flat_overrides_auto(self):
        org_config = {
            "agents": [
                _agent("A1", enabled=True),
                _agent("A2", enabled=True),
            ],
            "flat_mode_agents": ["A1"],
            "agent_final_weights": {},
        }
        result = self._derive_flat_agents(org_config)
        assert result == {"A1"}

    def test_explicit_weights_overrides_auto(self):
        org_config = {
            "agents": [
                _agent("A1", weight_score=1.5, enabled=True),
                _agent("A2", weight_score=0.8, enabled=True),
            ],
            "flat_mode_agents": [],
            "agent_final_weights": {"A1": 0.3},
        }
        result = self._derive_weights(org_config)
        assert result == {"A1": 0.3}
