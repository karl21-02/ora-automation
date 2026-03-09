from __future__ import annotations

import atexit
import json
import logging
import threading
import time
from typing import Callable, Literal

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from .config import settings

logger = logging.getLogger(__name__)


AgentRole = Literal[
    "ceo", "pm", "researcher", "engineer", "qa",
    "planner", "ops", "security_specialist", "linguist",
    "market_analyst", "finance_analyst", "ux_voice_designer",
    "data_scientist", "devops_sre", "qa_lead",
    "developer_backend", "developer_frontend", "developer_devops",
    "debate_supervisor", "web_search_agent", "search_evaluator",
]

RESEARCH_TARGETS = {
    "run",
    "run-direct",
    "run-cycle",
    "run-loop",
    "run-cycle-deep",
    "run-single",
    "verify-sources",
}

QA_TARGETS = {
    "e2e-service",
    "e2e-service-all",
    "qa-program",
    "qa-program-loop",
}


_ALL_ROLES = {
    "ceo", "pm", "researcher", "engineer", "qa",
    "planner", "ops", "security_specialist", "linguist",
    "market_analyst", "finance_analyst", "ux_voice_designer",
    "data_scientist", "devops_sre", "qa_lead",
    "developer_backend", "developer_frontend", "developer_devops",
    "debate_supervisor", "web_search_agent", "search_evaluator",
}

# Backward compatibility aliases
_ROLE_ALIASES: dict[str, str] = {
    "developer": "developer_backend",
    "developer_be": "developer_backend",
    "developer_fe": "developer_frontend",
}


def _normalize_role(role: str | None) -> AgentRole:
    raw = str(role or "").strip().lower()
    raw = _ROLE_ALIASES.get(raw, raw)
    if raw in _ALL_ROLES:
        return raw  # type: ignore[return-value]
    return "engineer"


def pick_agent_role(target: str, requested_role: str | None = None) -> AgentRole:
    role = _normalize_role(requested_role)
    if requested_role:
        return role
    if target in QA_TARGETS:
        return "qa"
    if target in RESEARCH_TARGETS:
        return "researcher"
    return "engineer"


def _routing_key_for_role(role: AgentRole) -> str:
    return f"agent.{role}"


def _retry_routing_key_for_role(role: AgentRole) -> str:
    return f"retry.{role}"


def _dead_routing_key_for_role(role: AgentRole) -> str:
    return f"dead.{role}"


def queue_name_for_role(role: AgentRole) -> str:
    return f"{settings.rabbitmq_queue_prefix}.{role}"


def retry_queue_name_for_role(role: AgentRole) -> str:
    return f"{settings.rabbitmq_queue_prefix}.{role}.retry"


def dlq_name_for_role(role: AgentRole) -> str:
    return f"{settings.rabbitmq_queue_prefix}.{role}.dlq"


class RabbitMQConnectionManager:
    """Thread-safe RabbitMQ connection manager with automatic reconnection.

    Encapsulates connection state, topology declaration, and cleanup logic.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conn: pika.BlockingConnection | None = None
        self._topology_declared = False

    def _connect(self) -> pika.BlockingConnection:
        """Create a new connection, closing any existing one first."""
        self._close_connection_unsafe()
        self._conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
        self._topology_declared = False
        return self._conn

    def _close_connection_unsafe(self) -> None:
        """Close connection without lock (caller must hold lock)."""
        if self._conn is not None:
            try:
                if self._conn.is_open:
                    self._conn.close()
            except Exception:
                logger.debug("Failed to close RabbitMQ connection during cleanup", exc_info=True)
            finally:
                self._conn = None
                self._topology_declared = False

    def _get_channel(self) -> pika.adapters.blocking_connection.BlockingChannel:
        """Get a channel, reconnecting if necessary (caller must hold lock)."""
        if self._conn is None or not self._conn.is_open:
            self._connect()
        assert self._conn is not None
        return self._conn.channel()

    def _declare_topology(self, channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
        """Declare exchanges and queues if not already done (caller must hold lock)."""
        if self._topology_declared:
            return

        channel.exchange_declare(
            exchange=settings.rabbitmq_exchange,
            exchange_type="direct",
            durable=True,
        )
        channel.exchange_declare(
            exchange=settings.rabbitmq_retry_exchange,
            exchange_type="direct",
            durable=True,
        )
        channel.exchange_declare(
            exchange=settings.rabbitmq_dlx_exchange,
            exchange_type="direct",
            durable=True,
        )

        for role in sorted(_ALL_ROLES):
            role_key: AgentRole = role  # type: ignore[assignment]
            main_queue = queue_name_for_role(role_key)
            retry_queue = retry_queue_name_for_role(role_key)
            dlq_queue = dlq_name_for_role(role_key)

            channel.queue_declare(queue=main_queue, durable=True)
            channel.queue_bind(
                exchange=settings.rabbitmq_exchange,
                queue=main_queue,
                routing_key=_routing_key_for_role(role_key),
            )

            channel.queue_declare(
                queue=retry_queue,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": settings.rabbitmq_exchange,
                    "x-dead-letter-routing-key": _routing_key_for_role(role_key),
                },
            )
            channel.queue_bind(
                exchange=settings.rabbitmq_retry_exchange,
                queue=retry_queue,
                routing_key=_retry_routing_key_for_role(role_key),
            )

            channel.queue_declare(queue=dlq_queue, durable=True)
            channel.queue_bind(
                exchange=settings.rabbitmq_dlx_exchange,
                queue=dlq_queue,
                routing_key=_dead_routing_key_for_role(role_key),
            )

        self._topology_declared = True

    def publish(
        self,
        publisher: Callable[[pika.adapters.blocking_connection.BlockingChannel], None],
        retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Execute a publish operation with automatic retry and reconnection.

        Args:
            publisher: Callback that performs the actual publish on the channel.
            retries: Number of retry attempts.
            retry_delay: Delay between retries in seconds.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(max(1, retries)):
            try:
                with self._lock:
                    channel = self._get_channel()
                    self._declare_topology(channel)
                    publisher(channel)
                return
            except (AMQPConnectionError, AMQPChannelError) as exc:
                last_error = exc
                logger.warning(
                    "RabbitMQ publish attempt %d/%d failed (connection error): %s",
                    attempt + 1, max(1, retries), exc,
                )
                with self._lock:
                    self._close_connection_unsafe()
            except Exception as exc:  # pragma: no cover
                # Unexpected error - still try to recover
                last_error = exc
                logger.warning(
                    "RabbitMQ publish attempt %d/%d failed (unexpected): %s",
                    attempt + 1, max(1, retries), exc,
                )
                with self._lock:
                    self._close_connection_unsafe()

            if attempt + 1 < max(1, retries):
                time.sleep(max(0.1, retry_delay))

        raise RuntimeError(f"rabbitmq publish failed: {last_error}")  # pragma: no cover

    def close(self) -> None:
        """Explicitly close the connection."""
        with self._lock:
            self._close_connection_unsafe()
        logger.debug("RabbitMQ connection manager closed")


# Singleton connection manager instance
_connection_manager = RabbitMQConnectionManager()


def _cleanup_connection() -> None:
    """Cleanup handler for graceful shutdown."""
    _connection_manager.close()


# Register cleanup handler
atexit.register(_cleanup_connection)


def publish_run(run_id: str, role: AgentRole, target: str, retries: int = 3, retry_delay: float = 1.0) -> None:
    """Publish a new run to the main exchange."""
    payload = {
        "run_id": run_id,
        "target": target,
        "agent_role": role,
    }

    def _publisher(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
        channel.basic_publish(
            exchange=settings.rabbitmq_exchange,
            routing_key=_routing_key_for_role(role),
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

    _connection_manager.publish(_publisher, retries=retries, retry_delay=retry_delay)


def publish_retry(
    run_id: str,
    role: AgentRole,
    target: str,
    delay_seconds: float,
    retries: int = 3,
    retry_delay: float = 1.0,
) -> None:
    """Publish a run to the retry exchange with a delay."""
    delay_ms = str(int(max(1.0, delay_seconds) * 1000.0))
    payload = {
        "run_id": run_id,
        "target": target,
        "agent_role": role,
        "retry_delay_seconds": delay_seconds,
    }

    def _publisher(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
        channel.basic_publish(
            exchange=settings.rabbitmq_retry_exchange,
            routing_key=_retry_routing_key_for_role(role),
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                expiration=delay_ms,
            ),
        )

    _connection_manager.publish(_publisher, retries=retries, retry_delay=retry_delay)


def publish_dlq(
    run_id: str,
    role: AgentRole,
    target: str,
    reason: str,
    retries: int = 3,
    retry_delay: float = 1.0,
) -> None:
    """Publish a run to the dead letter queue."""
    payload = {
        "run_id": run_id,
        "target": target,
        "agent_role": role,
        "reason": reason,
    }

    def _publisher(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
        channel.basic_publish(
            exchange=settings.rabbitmq_dlx_exchange,
            routing_key=_dead_routing_key_for_role(role),
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

    _connection_manager.publish(_publisher, retries=retries, retry_delay=retry_delay)
