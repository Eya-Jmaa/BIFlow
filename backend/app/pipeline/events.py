"""Pipeline event stream.

Events are published to Redis so the API can fan them out over SSE. Redis is
not required: when it is unavailable the events are kept in a bounded
in-process buffer instead, so a single-process run still streams its progress
and still has a replayable history. Losing the event bus must never take down
the pipeline that is emitting to it.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from typing import Any

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(service="events")

CHANNEL_PREFIX = "biflow:run:"
HISTORY_LIMIT = 500
HISTORY_TTL_SECONDS = 60 * 60 * 24

# How long to stay in fallback mode after a Redis failure before trying again.
# Without this, an absent Redis costs a DNS timeout on every single event.
_RETRY_COOLDOWN_SECONDS = 30.0

_lock = threading.Lock()
_fallback: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
_client: Any = None
_client_checked_at: float = 0.0
_client_failed: bool = False


def _redis():
    """Return a cached Redis client, or None while in cooldown after a failure."""
    global _client, _client_checked_at, _client_failed

    now = time.monotonic()
    if _client is not None:
        return _client
    if _client_failed and (now - _client_checked_at) < _RETRY_COOLDOWN_SECONDS:
        return None
    try:
        import redis

        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        client.ping()
    except Exception as exc:  # noqa: BLE001 - absence of Redis is expected
        _client_failed = True
        _client_checked_at = now
        if not _client_failed_logged():
            logger.info("redis_unavailable_using_memory_events", reason=str(exc))
        return None
    _client = client
    _client_failed = False
    _client_checked_at = now
    return client


_logged_once = False


def _client_failed_logged() -> bool:
    global _logged_once
    if _logged_once:
        return True
    _logged_once = True
    return False


def publish_event(run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    record = {
        "event": event_type,
        "run_id": run_id,
        "payload": payload or {},
        "ts": time.time(),
    }
    message = json.dumps(record, default=str)

    # The in-process buffer is always written, so history is available even
    # when Redis is healthy but this process is the only consumer.
    with _lock:
        _fallback[run_id].append(json.loads(message))

    client = _redis()
    if client is None:
        return
    try:
        client.publish(f"{CHANNEL_PREFIX}{run_id}", message)
        client.rpush(f"{CHANNEL_PREFIX}{run_id}:log", message)
        client.ltrim(f"{CHANNEL_PREFIX}{run_id}:log", -HISTORY_LIMIT, -1)
        client.expire(f"{CHANNEL_PREFIX}{run_id}:log", HISTORY_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        global _client, _client_failed, _client_checked_at
        _client = None
        _client_failed = True
        _client_checked_at = time.monotonic()
        # Note the structlog first positional is the message; a keyword named
        # "event" would collide with it and raise inside the error handler.
        logger.warning("event_publish_failed", run_id=run_id, event_type=event_type, error=str(exc))


def event_history(run_id: str, offset: int = 0) -> list[dict[str, Any]]:
    """Events for a run from ``offset`` onwards, newest last."""
    client = _redis()
    if client is not None:
        try:
            raw = client.lrange(f"{CHANNEL_PREFIX}{run_id}:log", offset, -1)
            if raw:
                return [json.loads(item) for item in raw]
        except Exception as exc:  # noqa: BLE001
            logger.warning("event_history_failed", run_id=run_id, error=str(exc))
    with _lock:
        return list(_fallback.get(run_id, ()))[offset:]


def clear_history(run_id: str) -> None:
    with _lock:
        _fallback.pop(run_id, None)
    client = _redis()
    if client is not None:
        try:
            client.delete(f"{CHANNEL_PREFIX}{run_id}:log")
        except Exception:  # noqa: BLE001
            pass
