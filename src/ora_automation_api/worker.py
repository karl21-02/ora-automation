from __future__ import annotations

import argparse
import json
import logging
import socket
import time
from uuid import uuid4

import pika

from .config import settings
from .queue import (
    AgentRole,
    dlq_name_for_role,
    pick_agent_role,
    publish_dlq,
    publish_retry,
    queue_name_for_role,
)
from .service import execute_run, recover_stale_runs


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [ora-automation-worker] %(message)s",
)
logger = logging.getLogger("ora_automation.worker")


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


def run_worker(agent_role: AgentRole) -> None:
    queue_name = queue_name_for_role(agent_role)
    reconnect_delay = max(0.5, settings.rabbitmq_reconnect_seconds)
    worker_id = _worker_id(agent_role)
    logger.info("worker boot | role=%s queue=%s dlq=%s worker_id=%s", agent_role, queue_name, dlq_name_for_role(agent_role), worker_id)

    last_recovery = 0.0
    recovery_interval = max(5.0, settings.heartbeat_interval_seconds * 2.0)

    while True:
        conn: pika.BlockingConnection | None = None
        try:
            conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
            channel = conn.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=max(1, settings.rabbitmq_prefetch))

            for method, _props, body in channel.consume(queue=queue_name, inactivity_timeout=1.0):
                now = time.monotonic()
                if now - last_recovery >= recovery_interval:
                    recovered = recover_stale_runs(stale_after_seconds=settings.stale_timeout_seconds)
                    for outcome in recovered:
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
                                reason=outcome.dlq_reason or "stale recovered to dlq",
                            )
                    last_recovery = now

                if method is None:
                    continue

                payload = _parse_payload(body)
                run_id = str(payload.get("run_id", "")).strip()
                target = str(payload.get("target", "")).strip()
                role = pick_agent_role(target, str(payload.get("agent_role", "")).strip())

                if not run_id:
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    continue

                outcome = execute_run(run_id=run_id, worker_id=worker_id)
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

                channel.basic_ack(delivery_tag=method.delivery_tag)

        except KeyboardInterrupt:
            logger.info("worker interrupted; stopping")
            break
        except Exception as exc:  # pragma: no cover
            logger.exception("worker loop error (role=%s): %s", agent_role, exc)
            time.sleep(reconnect_delay)
        finally:
            if conn and conn.is_open:
                try:
                    conn.close()
                except Exception:  # pragma: no cover
                    pass


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

