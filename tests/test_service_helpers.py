"""Tests for service.py helper functions.

These tests cover the internal helper functions that don't require
full integration setup.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ora_automation_api.service import (
    _normalize_stages,
    _pick_target,
    _resolve_fail_label,
    _retry_delay_seconds,
    _sanitize_env,
)


# ---------------------------------------------------------------------------
# _sanitize_env
# ---------------------------------------------------------------------------

class TestSanitizeEnv:
    def test_strips_whitespace_from_keys_and_values(self):
        result = _sanitize_env({"  KEY  ": "  value  "})
        assert result == {"KEY": "value"}

    def test_removes_empty_keys(self):
        result = _sanitize_env({"": "value", "   ": "other", "valid": "ok"})
        assert result == {"valid": "ok"}

    def test_converts_non_strings_to_strings(self):
        result = _sanitize_env({"num": 123, "bool": True})
        assert result == {"num": "123", "bool": "True"}

    def test_empty_dict_returns_empty(self):
        result = _sanitize_env({})
        assert result == {}


# ---------------------------------------------------------------------------
# _pick_target
# ---------------------------------------------------------------------------

class TestPickTarget:
    def test_returns_target_if_allowed(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.allowed_targets = ["rd-analysis", "e2e-test", "qa"]
            mock_settings.default_target = "rd-analysis"
            result = _pick_target("e2e-test")
            assert result == "e2e-test"

    def test_returns_default_if_target_not_allowed(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.allowed_targets = ["rd-analysis", "e2e-test"]
            mock_settings.default_target = "rd-analysis"
            result = _pick_target("invalid-target")
            assert result == "rd-analysis"

    def test_returns_first_allowed_if_default_not_allowed(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.allowed_targets = ["qa", "e2e-test"]
            mock_settings.default_target = "rd-analysis"  # not in allowed
            result = _pick_target("another-invalid")
            assert result == "qa"

    def test_none_target_returns_default(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.allowed_targets = ["rd-analysis", "e2e-test"]
            mock_settings.default_target = "rd-analysis"
            result = _pick_target(None)
            assert result == "rd-analysis"


# ---------------------------------------------------------------------------
# _normalize_stages
# ---------------------------------------------------------------------------

class TestNormalizeStages:
    def test_empty_list_returns_default(self):
        result = _normalize_stages([])
        assert result == ["analysis", "deliberation", "execution"]

    def test_adds_execution_if_missing(self):
        result = _normalize_stages(["analysis", "deliberation"])
        assert result == ["analysis", "deliberation", "execution"]

    def test_strips_and_lowercases(self):
        result = _normalize_stages(["  ANALYSIS  ", "  Deliberation  "])
        assert "analysis" in result
        assert "deliberation" in result
        assert "execution" in result

    def test_removes_duplicates(self):
        result = _normalize_stages(["analysis", "analysis", "deliberation"])
        assert result.count("analysis") == 1

    def test_preserves_order(self):
        result = _normalize_stages(["deliberation", "analysis"])
        assert result == ["deliberation", "analysis", "execution"]

    def test_execution_already_present_not_duplicated(self):
        result = _normalize_stages(["analysis", "execution", "deliberation"])
        assert result.count("execution") == 1


# ---------------------------------------------------------------------------
# _resolve_fail_label
# ---------------------------------------------------------------------------

class TestResolveFailLabel:
    def test_timed_out_returns_retry(self):
        run = MagicMock()
        run.env = {}
        result = _resolve_fail_label(run, timed_out=True)
        assert result == "RETRY"

    def test_env_skip_policy(self):
        run = MagicMock()
        run.env = {"PIPELINE_FAIL_DEFAULT": "SKIP"}
        result = _resolve_fail_label(run, timed_out=False)
        assert result == "SKIP"

    def test_env_stop_policy(self):
        run = MagicMock()
        run.env = {"PIPELINE_FAIL_DEFAULT": "STOP"}
        result = _resolve_fail_label(run, timed_out=False)
        assert result == "STOP"

    def test_env_retry_policy(self):
        run = MagicMock()
        run.env = {"PIPELINE_FAIL_DEFAULT": "RETRY"}
        result = _resolve_fail_label(run, timed_out=False)
        assert result == "RETRY"

    def test_invalid_policy_defaults_to_retry(self):
        run = MagicMock()
        run.env = {"PIPELINE_FAIL_DEFAULT": "INVALID"}
        result = _resolve_fail_label(run, timed_out=False)
        assert result == "RETRY"

    def test_empty_env_defaults_to_retry(self):
        run = MagicMock()
        run.env = {}
        result = _resolve_fail_label(run, timed_out=False)
        assert result == "RETRY"

    def test_none_env_defaults_to_retry(self):
        run = MagicMock()
        run.env = None
        result = _resolve_fail_label(run, timed_out=False)
        assert result == "RETRY"


# ---------------------------------------------------------------------------
# _retry_delay_seconds
# ---------------------------------------------------------------------------

class TestRetryDelaySeconds:
    def test_first_attempt_returns_base(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.retry_base_seconds = 5.0
            mock_settings.retry_max_seconds = 60.0
            result = _retry_delay_seconds(1)
            assert result == 5.0

    def test_second_attempt_doubles(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.retry_base_seconds = 5.0
            mock_settings.retry_max_seconds = 60.0
            result = _retry_delay_seconds(2)
            assert result == 10.0

    def test_third_attempt_quadruples(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.retry_base_seconds = 5.0
            mock_settings.retry_max_seconds = 60.0
            result = _retry_delay_seconds(3)
            assert result == 20.0

    def test_capped_at_max(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.retry_base_seconds = 5.0
            mock_settings.retry_max_seconds = 30.0
            # 5 * 2^4 = 80, but should be capped at 30
            result = _retry_delay_seconds(5)
            assert result == 30.0

    def test_zero_attempt_count(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.retry_base_seconds = 5.0
            mock_settings.retry_max_seconds = 60.0
            result = _retry_delay_seconds(0)
            # max(0, 0-1) = 0, so 5 * 2^0 = 5
            assert result == 5.0

    def test_negative_base_clamped_to_one(self):
        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.retry_base_seconds = -5.0
            mock_settings.retry_max_seconds = 60.0
            result = _retry_delay_seconds(1)
            assert result == 1.0  # max(1.0, -5) = 1.0


# ---------------------------------------------------------------------------
# _env_to_pipeline_kwargs
# ---------------------------------------------------------------------------

class TestEnvToPipelineKwargs:
    def test_default_values(self):
        from ora_automation_api.service import _env_to_pipeline_kwargs

        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.projects_root = Path("/projects")
            mock_settings.run_output_dir = Path("/output")
            result = _env_to_pipeline_kwargs({})

            assert result["workspace"] == Path("/projects")
            assert result["output_dir"] == Path("/output")
            assert result["top_k"] == 6
            assert result["output_name"] == "rd_research_report"
            assert result["max_files"] == 1500
            assert result["debate_rounds"] == 2
            assert result["orchestration_profile"] == "standard"
            assert result["agent_mode"] == "flat"

    def test_custom_values(self):
        from ora_automation_api.service import _env_to_pipeline_kwargs

        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.projects_root = Path("/default")
            mock_settings.run_output_dir = Path("/default-out")
            result = _env_to_pipeline_kwargs({
                "WORKSPACE": "/custom/workspace",
                "OUTPUT_DIR": "/custom/output",
                "TOP": "10",
                "OUTPUT_NAME": "custom_report",
                "MAX_FILES": "2000",
                "DEBATE_ROUNDS": "3",
                "ORCHESTRATION_PROFILE": "strict",
                "AGENT_MODE": "convergence",
                "FOCUS": "security",
                "VERSION_TAG": "V11",
            })

            assert result["workspace"] == Path("/custom/workspace")
            assert result["output_dir"] == Path("/custom/output")
            assert result["top_k"] == 10
            assert result["output_name"] == "custom_report"
            assert result["max_files"] == 2000
            assert result["debate_rounds"] == 3
            assert result["orchestration_profile"] == "strict"
            assert result["agent_mode"] == "convergence"
            assert result["report_focus"] == "security"
            assert result["version_tag"] == "V11"

    def test_csv_parsing(self):
        from ora_automation_api.service import _env_to_pipeline_kwargs

        with patch("ora_automation_api.service.settings") as mock_settings:
            mock_settings.projects_root = Path("/projects")
            mock_settings.run_output_dir = Path("/output")
            result = _env_to_pipeline_kwargs({
                "EXTENSIONS": "py,ts,js",
                "IGNORE_DIRS": "node_modules,build",
                "PIPELINE_STAGES": "analysis,execution",
                "PIPELINE_SERVICES": "auth,api",
            })

            assert result["extensions"] == ["py", "ts", "js"]
            assert result["ignore_dirs"] == {"node_modules", "build"}
            assert result["orchestration_stages"] == ["analysis", "execution"]
            assert result["service_scope"] == ["auth", "api"]
