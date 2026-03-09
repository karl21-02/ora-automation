"""Tests for RabbitMQ queue retry logging."""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from pika.exceptions import AMQPConnectionError


class TestConnectionManagerPublishLogging:
    """RabbitMQConnectionManager.publish logs on retry failures."""

    @patch("ora_automation_api.queue.RabbitMQConnectionManager._get_channel")
    def test_retry_failure_logs_warning(self, mock_channel, caplog):
        """Each failed publish attempt logs a warning."""
        from ora_automation_api.queue import _connection_manager

        mock_channel.side_effect = AMQPConnectionError("refused")

        with caplog.at_level(logging.WARNING, logger="ora_automation_api.queue"):
            with pytest.raises(RuntimeError, match="rabbitmq publish failed"):
                _connection_manager.publish(lambda ch: None, retries=2, retry_delay=0.01)

        warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_msgs) == 2
        assert "attempt 1/2" in warning_msgs[0].message
        assert "attempt 2/2" in warning_msgs[1].message

    @patch("ora_automation_api.queue.RabbitMQConnectionManager._get_channel")
    def test_single_retry_logs_once(self, mock_channel, caplog):
        """Single retry = single warning."""
        from ora_automation_api.queue import _connection_manager

        mock_channel.side_effect = AMQPConnectionError("timeout")

        with caplog.at_level(logging.WARNING, logger="ora_automation_api.queue"):
            with pytest.raises(RuntimeError, match="rabbitmq publish failed"):
                _connection_manager.publish(lambda ch: None, retries=1, retry_delay=0.01)

        warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_msgs) == 1
        assert "attempt 1/1" in warning_msgs[0].message
