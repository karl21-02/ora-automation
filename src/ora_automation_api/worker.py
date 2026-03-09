from __future__ import annotations

import argparse
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pika

from .config import settings
from .logging_config import get_logger, setup_logging
from .queue import (
    AgentRole,
    dlq_name_for_role,
    pick_agent_role,
    publish_dlq,
    publish_retry,
    queue_name_for_role,
)
from .service import execute_run, recover_stale_runs

# Initialize logging for worker process
setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger("ora_automation.worker")


def _parse_payload(body: bytes) -> dict:
    raw = (body or b"").decode("utf-8", errors="ignore").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"run_id": raw}


def _worker_id(role: AgentRole) -> str:
    return f"{role}@{socket.gethostname()}:{uuid4().hex[:8]}"


class PipelineWorker:
    """RabbitMQ consumer with ThreadPoolExecutor for concurrent pipeline runs."""

    def __init__(self, agent_role: AgentRole, max_concurrent: int = 2) -> None:
        self._role = agent_role
        self._queue_name = queue_name_for_role(agent_role)
        self._worker_id = _worker_id(agent_role)
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_concurrent))
        self._running = True

    def _handle_outcome(self, outcome) -> None:
        if outcome.should_retry:
            publish_retry(
                run_id=outcome.run_id,
                role=outcome.agent_role,
                target=outcome.target,
                delay_seconds=outcome.retry_delay_seconds,
            )
        elif outcome.should_dlq:
            publish_dlq(
                run_id=outcome.run_id,
                role=outcome.agent_role,
                target=outcome.target,
                reason=outcome.dlq_reason or "policy stop",
            )

    def _execute_one(self, run_id: str) -> None:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            outcome = execute_run(run_id=run_id, worker_id=self._worker_id, db=db)
            self._handle_outcome(outcome)
        except Exception:
            logger.exception("Error executing run %s", run_id)
        finally:
            db.close()

    def run(self) -> None:
        reconnect_delay = max(0.5, settings.rabbitmq_reconnect_seconds)
        logger.info(
            "worker boot | role=%s queue=%s dlq=%s worker_id=%s max_concurrent=%d",
            self._role, self._queue_name, dlq_name_for_role(self._role),
            self._worker_id, self._executor._max_workers,
        )

        last_recovery = 0.0
        recovery_interval = max(5.0, settings.heartbeat_interval_seconds * 2.0)

        while self._running:
            conn: pika.BlockingConnection | None = None
            try:
                conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
                channel = conn.channel()
                channel.queue_declare(queue=self._queue_name, durable=True)
                channel.basic_qos(prefetch_count=max(1, settings.rabbitmq_prefetch))

                for method, _props, body in channel.consume(queue=self._queue_name, inactivity_timeout=1.0):
                    if not self._running:
                        break

                    now = time.monotonic()
                    if now - last_recovery >= recovery_interval:
                        recovered = recover_stale_runs(stale_after_seconds=settings.stale_timeout_seconds)
                        for outcome in recovered:
                            self._handle_outcome(outcome)
                        last_recovery = now

                    if method is None:
                        continue

                    payload = _parse_payload(body)
                    run_id = str(payload.get("run_id", "")).strip()

                    if not run_id:
                        channel.basic_ack(delivery_tag=method.delivery_tag)
                        continue

                    self._executor.submit(self._execute_one, run_id)
                    channel.basic_ack(delivery_tag=method.delivery_tag)

            except KeyboardInterrupt:
                logger.info("worker interrupted; stopping")
                self._running = False
                break
            except Exception as exc:  # pragma: no cover
                logger.exception("worker loop error (role=%s): %s", self._role, exc)
                time.sleep(reconnect_delay)
            finally:
                if conn and conn.is_open:
                    try:
                        conn.close()
                    except Exception:  # pragma: no cover
                        pass

        self._executor.shutdown(wait=True, cancel_futures=False)

    def stop(self) -> None:
        self._running = False


def run_worker(agent_role: AgentRole) -> None:
    worker = PipelineWorker(
        agent_role=agent_role,
        max_concurrent=settings.worker_max_concurrent,
    )
    worker.run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ora-automation RabbitMQ worker")
    parser.add_argument(
        "--agent-role",
        choices=["ceo", "pm", "researcher", "engineer", "qa"],
        default="engineer",
    )
    args = parser.parse_args(argv)
    run_worker(args.agent_role)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
