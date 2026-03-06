"""Tests for _run_pipeline threading, heartbeat, timeout, env→kwargs."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ora_automation_api.service import PipelineOutcome, _env_to_pipeline_kwargs


class TestEnvToPipelineKwargs:
    """Test _env_to_pipeline_kwargs converts env dict to generate_report() kwargs."""

    def test_default_values(self):
        kwargs = _env_to_pipeline_kwargs({})
        assert kwargs["top_k"] == 6
        assert kwargs["max_files"] == 1500
        assert kwargs["debate_rounds"] == 2
        assert kwargs["output_name"] == "rd_research_report"
        assert kwargs["version_tag"] == "V10"
        assert kwargs["orchestration_profile"] == "standard"

    def test_custom_values(self):
        env = {
            "TOP": "10",
            "MAX_FILES": "2000",
            "DEBATE_ROUNDS": "3",
            "OUTPUT_NAME": "custom_report",
            "VERSION_TAG": "V20",
            "ORCHESTRATION_PROFILE": "strict",
            "FOCUS": "security",
        }
        kwargs = _env_to_pipeline_kwargs(env)
        assert kwargs["top_k"] == 10
        assert kwargs["max_files"] == 2000
        assert kwargs["debate_rounds"] == 3
        assert kwargs["output_name"] == "custom_report"
        assert kwargs["version_tag"] == "V20"
        assert kwargs["orchestration_profile"] == "strict"
        assert kwargs["report_focus"] == "security"

    def test_extensions_csv_parsing(self):
        env = {"EXTENSIONS": "py,ts,tsx"}
        kwargs = _env_to_pipeline_kwargs(env)
        assert kwargs["extensions"] == ["py", "ts", "tsx"]

    def test_pipeline_stages_parsing(self):
        env = {"PIPELINE_STAGES": "analysis,execution"}
        kwargs = _env_to_pipeline_kwargs(env)
        assert kwargs["orchestration_stages"] == ["analysis", "execution"]

    def test_workspace_path(self):
        env = {"WORKSPACE": "/tmp/test_workspace"}
        kwargs = _env_to_pipeline_kwargs(env)
        # resolve() will normalize; just check the path ends correctly
        assert str(kwargs["workspace"]).endswith("test_workspace")

    def test_output_dir_path(self):
        env = {"OUTPUT_DIR": "/tmp/test_output"}
        kwargs = _env_to_pipeline_kwargs(env)
        assert str(kwargs["output_dir"]).endswith("test_output")

    def test_ignore_dirs_set(self):
        env = {"IGNORE_DIRS": ".git,node_modules,.venv"}
        kwargs = _env_to_pipeline_kwargs(env)
        assert isinstance(kwargs["ignore_dirs"], set)
        assert ".git" in kwargs["ignore_dirs"]
        assert "node_modules" in kwargs["ignore_dirs"]


class TestPipelineOutcome:
    """Test PipelineOutcome dataclass."""

    def test_default_is_success(self):
        outcome = PipelineOutcome()
        assert outcome.result == {}
        assert outcome.error is None
        assert not outcome.timed_out
        assert not outcome.cancelled

    def test_error_outcome(self):
        outcome = PipelineOutcome(error=("error", "something broke"))
        assert outcome.error is not None
        assert outcome.error[0] == "error"
        assert outcome.error[1] == "something broke"

    def test_timeout_outcome(self):
        outcome = PipelineOutcome(timed_out=True)
        assert outcome.timed_out

    def test_cancelled_outcome(self):
        outcome = PipelineOutcome(cancelled=True)
        assert outcome.cancelled

    def test_result_with_data(self):
        outcome = PipelineOutcome(result={"report_path": "/tmp/report.md"})
        assert outcome.result["report_path"] == "/tmp/report.md"


class TestLoadOrgConfig:
    """Test _load_org_config loads org + agents from DB."""

    @pytest.fixture()
    def db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from ora_automation_api.database import Base

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()
        engine.dispose()

    def test_none_org_id_returns_none(self, db):
        from ora_automation_api.service import _load_org_config
        assert _load_org_config(db, None) is None

    def test_missing_org_returns_none(self, db):
        from ora_automation_api.service import _load_org_config
        assert _load_org_config(db, "nonexistent-id") is None

    def test_loads_org_with_agents(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationAgent
        from ora_automation_api.service import _load_org_config

        org = Organization(
            id=uuid4().hex[:36],
            name="TestOrg",
            teams={"strategy": ["CEO"]},
            flat_mode_agents=["CEO", "PM"],
            agent_final_weights={"CEO": 0.5, "PM": 0.5},
        )
        db.add(org)
        db.flush()

        agent = OrganizationAgent(
            id=uuid4().hex[:36],
            org_id=org.id,
            agent_id="CEO",
            display_name="CEO",
            display_name_ko="대표",
            role="ceo",
            tier=4,
            team="strategy",
            personality={"archetype": "leader"},
            behavioral_directives=["lead"],
            constraints=[],
            decision_focus=["impact"],
            weights={"impact": 0.5},
            trust_map={"PM": 0.8},
        )
        db.add(agent)
        db.commit()

        config = _load_org_config(db, org.id)
        assert config is not None
        assert config["org_name"] == "TestOrg"
        assert len(config["agents"]) == 1
        assert config["agents"][0]["agent_id"] == "CEO"
        assert config["flat_mode_agents"] == ["CEO", "PM"]
        assert config["agent_final_weights"]["CEO"] == 0.5
