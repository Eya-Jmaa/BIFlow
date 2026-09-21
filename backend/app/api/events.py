from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.pipeline.events import CHANNEL_PREFIX, event_history

router = APIRouter()

# An SSE connection without Redis polls the in-process buffer; it gives up
# rather than holding the connection open forever if a run never terminates.
POLL_TIMEOUT_SECONDS = 60 * 30


@router.get("/pipeline-runs/{run_id}/stream")
async def stream_run(run_id: UUID):
    terminal = {"pipeline.completed", "pipeline.failed"}

    async def events():
        replayed = event_history(str(run_id))
        for item in replayed:
            yield {"event": item.get("event", "message"), "data": json.dumps(item)}
        if replayed and replayed[-1].get("event") in terminal:
            return
        cursor = len(replayed)

        try:
            import redis.asyncio as redis

            client = redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
            await client.ping()
            pubsub = client.pubsub()
            await pubsub.subscribe(f"{CHANNEL_PREFIX}{run_id}")
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                parsed = json.loads(data)
                yield {"event": parsed.get("event", "message"), "data": data}
                if parsed.get("event") in terminal:
                    break
            return
        except Exception:
            # No Redis: fall back to polling the in-process buffer. The cursor
            # stops the same event being re-sent on every tick.
            deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SECONDS
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(1)
                pending = event_history(str(run_id), offset=cursor)
                cursor += len(pending)
                finished = False
                for item in pending:
                    yield {"event": item.get("event", "message"), "data": json.dumps(item)}
                    if item.get("event") in terminal:
                        finished = True
                if finished:
                    break

    return EventSourceResponse(events())
