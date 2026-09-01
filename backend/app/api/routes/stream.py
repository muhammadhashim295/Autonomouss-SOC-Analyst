"""Phase 14 — SSE streaming endpoint.

``POST /alerts/{alert_id}/investigate/stream``

Runs the full dual-agent investigation (same pipeline as
``/reinvestigate``) and relays every stage to the client as
Server-Sent Events the moment it happens — the agents' reasoning
arrives progressively via ``agent_delta`` events, not as one blob at
the end.

Design notes:

- POST rather than GET: the browser client uses ``fetch()`` +
  ReadableStream (``EventSource`` cannot POST), which also guarantees
  an automatic reconnect can never accidentally re-trigger an
  investigation.
- The pipeline is synchronous and long-running, so it executes in a
  producer thread pushing events onto a queue; the async generator
  relays them and emits ``: heartbeat`` comments during silent
  stretches (agent thinking / OTX calls) so proxies don't close the
  connection as idle.
- Errors mid-stream become an ``investigation_error`` event (the HTTP
  status is already committed by then) and the alert is reverted to
  ``pending`` for retry — mirroring the endpoint contract.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db.supabase_client import get_supabase
from app.services.investigation_stream import run_dual_agent_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["stream"])

# Seconds of stream silence before emitting a heartbeat comment
_HEARTBEAT_SECONDS = 15.0


@router.post("/{alert_id}/investigate/stream")
async def stream_investigation(alert_id: str) -> StreamingResponse:
    """Stream a full dual-agent investigation as live SSE events."""
    client = get_supabase()

    result = client.table("alerts").select("*").eq("id", alert_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert = result.data[0]

    client.table("alerts").update({"status": "in_review"}).eq(
        "id", alert_id
    ).execute()

    events: "queue.Queue[dict[str, Any] | None]" = queue.Queue()

    def produce() -> None:
        """Run the pipeline in a worker thread, pushing events to the queue."""
        try:
            for event in run_dual_agent_stream(alert):
                events.put(event)
        except Exception as exc:  # noqa: BLE001 — surfaced to the client
            logger.error(
                "Investigation stream failed for %s: %s", alert_id, exc
            )
            events.put(
                {
                    "event": "investigation_error",
                    "data": {"detail": f"{type(exc).__name__}: {exc}"},
                }
            )
            # Mirror the endpoint contract: revert so the alert can retry
            get_supabase().table("alerts").update({"status": "pending"}).eq(
                "id", alert_id
            ).execute()
        finally:
            events.put(None)  # sentinel — stream over

    threading.Thread(
        target=produce, daemon=True, name=f"sse-{alert_id[:8]}"
    ).start()

    async def event_stream():
        while True:
            try:
                item = await asyncio.to_thread(
                    events.get, True, _HEARTBEAT_SECONDS
                )
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            if item is None:
                break
            payload = json.dumps(item["data"], ensure_ascii=False, default=str)
            yield f"event: {item['event']}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )
