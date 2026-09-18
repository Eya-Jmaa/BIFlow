from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.pipeline.events import CHANNEL_PREFIX, event_history

router = APIRouter()


@router.get("/pipeline-runs/{run_id}/stream")
async def stream_run(run_id: UUID):
    async def events():
        for item in event_history(str(run_id)):
            yield {"event": item.get("event", "message"), "data": json.dumps(item)}
        try:
            import redis.asyncio as redis

            client = redis.from_url(get_settings().redis_url)
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
                if parsed.get("event") in {"pipeline.completed", "pipeline.failed"}:
                    break
        except Exception:
            while True:
                await asyncio.sleep(2)
                history = event_history(str(run_id))
                if history:
                    last = history[-1]
                    yield {"event": last.get("event", "message"), "data": json.dumps(last)}
                    if last.get("event") in {"pipeline.completed", "pipeline.failed"}:
                        break

    return EventSourceResponse(events())
