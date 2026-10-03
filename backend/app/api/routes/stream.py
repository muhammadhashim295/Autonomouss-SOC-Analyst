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
- The pre-flight reads happen *before* that status is committed, so a
  transient Supabase blip there would otherwise surface as a bare HTTP
  500 and leave the UI with a frozen pipeline.  They are translated into
  an explicit 503 the client can retry instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.auth import CurrentUser, get_optional_user
from app.db.supabase_client import get_supabase
from app.services.investigation_stream import run_dual_agent_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["stream"])

# Seconds of stream silence before emitting a heartbeat comment
_HEARTBEAT_SECONDS = 15.0


@router.post("/{alert_id}/investigate/stream")
async def stream_investigation(
    alert_id: str,
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
) -> StreamingResponse:
    """Stream a full dual-agent investigation as live SSE events."""
    client = get_supabase()

    # ── Pre-flight: these run before the SSE status is committed, so any
    #    transient storage failure must become a retryable 503 rather than a
    #    raw 500 (which the UI can only report as "HTTP 500" on a dead run).
    try:
        result = client.table("alerts").select("*").eq("id", alert_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error("Alert fetch failed for stream %s: %s", alert_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Alert store unavailable — please retry the investigation.",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert = result.data[0]

    if current_user and current_user.is_client and current_user.org_id:
        if alert.get("org_id") and str(alert.get("org_id")) != str(current_user.org_id):
            raise HTTPException(
                status_code=403,
                detail="Forbidden: You do not have access to this tenant's alert.",
            )

    try:
        client.table("alerts").update({"status": "in_review"}).eq(
            "id", alert_id
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not mark alert %s in_review: %s", alert_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Alert store unavailable — please retry the investigation.",
        ) from exc

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
            try:
                get_supabase().table("alerts").update({"status": "pending"}).eq(
                    "id", alert_id
                ).execute()
            except Exception:  # noqa: BLE001 — never mask the reported error
                logger.exception(
                    "Could not revert alert %s to pending after a stream error", alert_id
                )
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
        # Explicit charset so the browser (and any intermediary) decodes the
        # UTF-8 reasoning stream correctly — matches the frontend TextDecoder.
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )
