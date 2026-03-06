"""Tests for Settings._validate() — range clamping and warnings."""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest


def _make_settings(**env_overrides):
    """Build a Settings instance with given env overrides."""
    defaults = {
        "DATABASE_URL": "sqlite:///:memory:",
        "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/%2F",
        "ORA_AUTOMATION_ROOT": "/tmp/ora-test",
    }
    defaults.update(env_overrides)
    with patch.dict("os.environ", defaults, clear=False):
        from ora_automation_api.config import Settings
        return Settings()


class TestSettingsValidation:
    """Settings._validate() clamps invalid values and logs warnings."""

    def test_negative_timeout_clamped(self, caplog):
        with caplog.at_level(logging.WARNING, logger="ora_automation_api.config"):
            s = _make_settings(ORA_AUTOMATION_COMMAND_TIMEOUT="-100")
        assert s.default_timeout_seconds == 3600.0
        assert any("default_timeout_seconds" in m for m in caplog.messages)

    def test_zero_heartbeat_clamped(self, caplog):
        with caplog.at_level(logging.WARNING, logger="ora_automation_api.config"):
            s = _make_settings(ORA_AUTOMATION_HEARTBEAT_INTERVAL_SECONDS="0")
        assert s.heartbeat_interval_seconds == 2.0

    def test_negative_stale_timeout_clamped(self):
        s = _make_settings(ORA_AUTOMATION_STALE_TIMEOUT_SECONDS="-1")
        assert s.stale_timeout_seconds == 120.0

    def test_zero_max_attempts_clamped(self):
        s = _make_settings(ORA_AUTOMATION_MAX_ATTEMPTS="0")
        assert s.default_max_attempts == 1

    def test_scheduler_poll_below_10_clamped(self, caplog):
        with caplog.at_level(logging.WARNING, logger="ora_automation_api.config"):
            s = _make_settings(ORA_SCHEDULER_POLL_SECONDS="5")
        assert s.scheduler_poll_seconds == 10
        assert any("scheduler_poll_seconds" in m for m in caplog.messages)

    def test_scheduler_poll_at_10_accepted(self):
        s = _make_settings(ORA_SCHEDULER_POLL_SECONDS="10")
        assert s.scheduler_poll_seconds == 10

    def test_rabbitmq_prefetch_zero_clamped(self):
        s = _make_settings(RABBITMQ_PREFETCH="0")
        assert s.rabbitmq_prefetch == 1

    def test_default_target_not_in_allowed_adds_it(self, caplog):
        with caplog.at_level(logging.WARNING, logger="ora_automation_api.config"):
            s = _make_settings(ORA_AUTOMATION_DEFAULT_TARGET="custom-target")
        assert "custom-target" in s.allowed_targets
        assert any("default_target" in m for m in caplog.messages)

    def test_valid_settings_no_warnings(self, caplog):
        with caplog.at_level(logging.WARNING, logger="ora_automation_api.config"):
            s = _make_settings()
        config_warnings = [m for m in caplog.messages if "ora_automation_api.config" in caplog.records[caplog.messages.index(m)].name] if caplog.messages else []
        assert len(config_warnings) == 0
        assert s.default_timeout_seconds == 3600.0
        assert s.scheduler_poll_seconds == 60
