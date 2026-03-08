"""Tests for Pydantic input validation on Organization schemas."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ora_automation_api.schemas import (
    OrgAgentCreate,
    OrgAgentUpdate,
    OrgChapterCreate,
    OrgChapterUpdate,
)


class TestAgentIdValidation:
    """agent_id must be 3-64 chars, start with letter, contain only [A-Za-z0-9_]."""

    def test_valid_agent_id(self):
        agent = OrgAgentCreate(agent_id="CEO", display_name="CEO")
        assert agent.agent_id == "CEO"

    def test_valid_agent_id_with_underscore(self):
        agent = OrgAgentCreate(agent_id="Developer_BE", display_name="Dev")
        assert agent.agent_id == "Developer_BE"

    def test_valid_agent_id_with_numbers(self):
        agent = OrgAgentCreate(agent_id="Agent123", display_name="Agent")
        assert agent.agent_id == "Agent123"

    def test_agent_id_too_short(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="AB", display_name="Too Short")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_too_long(self):
        long_id = "A" * 65
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id=long_id, display_name="Too Long")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_starts_with_number_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="123Agent", display_name="Bad")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_starts_with_underscore_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="_Agent", display_name="Bad")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_with_hyphen_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="Agent-Name", display_name="Bad")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_with_space_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="Agent Name", display_name="Bad")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_with_special_chars_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="Agent@Name", display_name="Bad")
        assert "agent_id" in str(exc_info.value)

    def test_agent_id_korean_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(agent_id="에이전트", display_name="Bad")
        assert "agent_id" in str(exc_info.value)


class TestSystemPromptValidation:
    """system_prompt_template max 4000 chars."""

    def test_valid_system_prompt(self):
        prompt = "You are a helpful agent." * 10
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            system_prompt_template=prompt,
        )
        assert agent.system_prompt_template == prompt

    def test_system_prompt_at_limit(self):
        prompt = "A" * 4000
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            system_prompt_template=prompt,
        )
        assert len(agent.system_prompt_template) == 4000

    def test_system_prompt_over_limit_rejected(self):
        prompt = "A" * 4001
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(
                agent_id="TestAgent",
                display_name="Test",
                system_prompt_template=prompt,
            )
        assert "system_prompt_template" in str(exc_info.value)

    def test_update_system_prompt_over_limit_rejected(self):
        prompt = "A" * 4001
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentUpdate(system_prompt_template=prompt)
        assert "system_prompt_template" in str(exc_info.value)


class TestChapterPromptValidation:
    """chapter_prompt max 2000 chars."""

    def test_valid_chapter_prompt(self):
        prompt = "You belong to the Engineering chapter."
        chapter = OrgChapterCreate(name="Engineering", chapter_prompt=prompt)
        assert chapter.chapter_prompt == prompt

    def test_chapter_prompt_at_limit(self):
        prompt = "B" * 2000
        chapter = OrgChapterCreate(name="Test", chapter_prompt=prompt)
        assert len(chapter.chapter_prompt) == 2000

    def test_chapter_prompt_over_limit_rejected(self):
        prompt = "B" * 2001
        with pytest.raises(ValidationError) as exc_info:
            OrgChapterCreate(name="Test", chapter_prompt=prompt)
        assert "chapter_prompt" in str(exc_info.value)

    def test_update_chapter_prompt_over_limit_rejected(self):
        prompt = "B" * 2001
        with pytest.raises(ValidationError) as exc_info:
            OrgChapterUpdate(chapter_prompt=prompt)
        assert "chapter_prompt" in str(exc_info.value)


class TestDisplayNameValidation:
    """display_name_ko max 256 chars."""

    def test_valid_display_name_ko(self):
        agent = OrgAgentCreate(
            agent_id="CEO",
            display_name="CEO",
            display_name_ko="CEO (수주 적중률에 집착하는 사업 총괄)",
        )
        assert "수주 적중률" in agent.display_name_ko

    def test_display_name_ko_at_limit(self):
        name_ko = "가" * 256
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            display_name_ko=name_ko,
        )
        assert len(agent.display_name_ko) == 256

    def test_display_name_ko_over_limit_rejected(self):
        name_ko = "가" * 257
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(
                agent_id="TestAgent",
                display_name="Test",
                display_name_ko=name_ko,
            )
        assert "display_name_ko" in str(exc_info.value)


class TestWeightScoreValidation:
    """weight_score must be 0.0 to 10.0."""

    def test_valid_weight_score(self):
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            weight_score=1.5,
        )
        assert agent.weight_score == 1.5

    def test_weight_score_zero(self):
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            weight_score=0.0,
        )
        assert agent.weight_score == 0.0

    def test_weight_score_max(self):
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            weight_score=10.0,
        )
        assert agent.weight_score == 10.0

    def test_weight_score_negative_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(
                agent_id="TestAgent",
                display_name="Test",
                weight_score=-0.1,
            )
        assert "weight_score" in str(exc_info.value)

    def test_weight_score_over_max_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(
                agent_id="TestAgent",
                display_name="Test",
                weight_score=10.1,
            )
        assert "weight_score" in str(exc_info.value)


class TestTierValidation:
    """tier must be 1 to 4."""

    def test_valid_tier(self):
        agent = OrgAgentCreate(
            agent_id="TestAgent",
            display_name="Test",
            tier=3,
        )
        assert agent.tier == 3

    def test_tier_zero_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(
                agent_id="TestAgent",
                display_name="Test",
                tier=0,
            )
        assert "tier" in str(exc_info.value)

    def test_tier_five_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OrgAgentCreate(
                agent_id="TestAgent",
                display_name="Test",
                tier=5,
            )
        assert "tier" in str(exc_info.value)
