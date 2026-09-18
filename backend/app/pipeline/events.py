from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(service="events")

CHANNEL_PREFIX = "biflow:run:"


def _redis():
    import redis

    return redis.from_url(get_settings().redis_url)


def publish_event(run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    message = json.dumps({"event": event_type, "run_id": run_id, "payload": payload or {}}, default=str)
    try:
        client = _redis()
        client.publish(f"{CHANNEL_PREFIX}{run_id}", message)
        client.rpush(f"{CHANNEL_PREFIX}{run_id}:log", message)
        client.expire(f"{CHANNEL_PREFIX}{run_id}:log", 60 * 60 * 24)
    except Exception as exc:
        logger.warning("event_publish_failed", run_id=run_id, event=event_type, error=str(exc))


def event_history(run_id: str) -> list[dict[str, Any]]:
    try:
        client = _redis()
        raw = client.lrange(f"{CHANNEL_PREFIX}{run_id}:log", 0, -1)
        return [json.loads(item) for item in raw]
    except Exception:
        return []
