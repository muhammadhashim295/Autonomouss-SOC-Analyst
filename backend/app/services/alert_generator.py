"""Background Cloudflare Workers AI alert generator for the live Command Center.

Runs as an asyncio task, generating alerts at a configurable interval (default
3s — the stable point of the 2-3s window).  Live runs require a successful
Cloudflare Workers AI response and never substitute scripted payload templates
when Cloudflare is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.core.config import settings
from app.core.firewall import check_alert, sanitize_snippet
from app.db.supabase_client import get_supabase
from app.services.cloudflare_client import CloudflareClient, CloudflareGenerationError

logger = logging.getLogger(__name__)


class _GeneratorState:
    """Tracks the current generation run."""

    def __init__(self) -> None:
        self.active: bool = False
        self.run_id: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.alerts_generated: int = 0
        self.poison_injected: int = 0
        self.firewall_caught: int = 0
        self.total_planned: int = 0
        self.duration_seconds: int = 120
        self.interval_seconds: int = settings.live_feed_interval_seconds
        self.poison_ratio: float = settings.live_feed_poison_ratio
        self.last_error: Optional[str] = None
        self._task: Optional[asyncio.Task[None]] = None

    def to_status_dict(self) -> dict[str, Any]:
        """Return the current state as a JSON-serialisable dict."""
        if not self.active:
            status: dict[str, Any] = {"status": "idle", "generator": "cloudflare"}
            if self.last_error:
                status["last_error"] = self.last_error
            return status

        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()  # type: ignore[operator]
        remaining = max(0, self.duration_seconds - int(elapsed))
        return {
            "status": "running",
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),  # type: ignore[union-attr]
            "alerts_generated": self.alerts_generated,
            "poison_injected": self.poison_injected,
            "firewall_caught": self.firewall_caught,
            "total_planned": self.total_planned,
            "alerts_remaining": max(0, self.total_planned - self.alerts_generated),
            "estimated_seconds_left": remaining,
            "poison_ratio": self.poison_ratio,
            "interval_seconds": self.interval_seconds,
            "generator": "cloudflare",
            "last_error": self.last_error,
        }


# Module-level singleton
_state = _GeneratorState()


def get_generator_status() -> dict[str, Any]:
    """Return the current generator status."""
    return _state.to_status_dict()


def start_generation(
    duration_seconds: int = 120,
    interval_seconds: Optional[int] = None,
    poison_ratio: Optional[float] = None,
) -> dict[str, Any]:
    """Start a new alert generation run.

    Returns the run details.  The actual generation happens in an asyncio
    background task — this function returns immediately.  ``interval_seconds``
    defaults to ``settings.live_feed_interval_seconds`` (3s) and ``poison_ratio``
    to ``settings.live_feed_poison_ratio`` (~15%).
    """
    if _state.active:
        raise RuntimeError("A generation run is already active")

    interval_seconds = (
        settings.live_feed_interval_seconds if interval_seconds is None else interval_seconds
    )
    poison_ratio = (
        settings.live_feed_poison_ratio if poison_ratio is None else poison_ratio
    )

    if not CloudflareClient().available:
        raise CloudflareGenerationError(
            "Cloudflare Workers AI is unavailable; set CLOUDFLARE_API_TOKEN and "
            "CLOUDFLARE_ACCOUNT_ID. No scripted alerts will be generated."
        )

    run_id = str(uuid4())[:8]
    # The first Cloudflare request runs immediately, then repeats per interval.
    total_planned = max(1, (duration_seconds + interval_seconds - 1) // interval_seconds)

    _state.active = True
    _state.run_id = run_id
    _state.started_at = datetime.now(timezone.utc)
    _state.alerts_generated = 0
    _state.poison_injected = 0
    _state.firewall_caught = 0
    _state.total_planned = total_planned
    _state.duration_seconds = duration_seconds
    _state.interval_seconds = interval_seconds
    _state.poison_ratio = poison_ratio
    _state.last_error = None

    # Launch the background asyncio task
    _state._task = asyncio.create_task(
        _generate_loop(duration_seconds, interval_seconds, poison_ratio)
    )

    return {
        "status": "started",
        "run_id": run_id,
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "poison_ratio": poison_ratio,
        "estimated_alerts": total_planned,
        "started_at": _state.started_at.isoformat(),
        "generator": "cloudflare",
    }


def stop_generation() -> dict[str, Any]:
    """Cancel the current generation run.

    Returns the final counts.  Raises RuntimeError if no run is active.
    """
    if not _state.active:
        raise RuntimeError("No generation run is active")

    if _state._task is not None:
        _state._task.cancel()

    result = {
        "status": "stopped",
        "run_id": _state.run_id,
        "alerts_generated": _state.alerts_generated,
        "poison_injected": _state.poison_injected,
        "firewall_caught": _state.firewall_caught,
    }

    _state.active = False
    _state._task = None
    return result


# ── Internal ──────────────────────────────────────────────────────────────────


async def _generate_loop(
    duration_seconds: int,
    interval_seconds: int,
    poison_ratio: float,
) -> None:
    """Async live-feed loop built on a small pool of concurrent Cloudflare workers.

    A single Cloudflare Workers AI call takes ~3-8s, so one sequential worker
    cannot sustain a 3s cadence — the feed would drift to the call latency.
    Instead ``settings.live_feed_concurrency`` workers generate alerts in
    parallel into a bounded queue, and a single inserter drains the queue once
    per ``interval_seconds`` tick.  Because the workers produce faster than the
    inserter drains, the queue stays stocked and the observable cadence is the
    configured interval regardless of per-call latency.

    Runs as an asyncio.Task.  Each inserter tick:
    1. Pops one pre-generated alert from the queue
    2. Runs the firewall check on the payload
    3. Inserts the alert into Supabase (off the event loop)
    4. Inserts firewall_flags if the firewall caught something
    """
    import random

    cloudflare = CloudflareClient()
    supabase = get_supabase()
    concurrency = max(1, settings.live_feed_concurrency)
    end_time = datetime.now(timezone.utc).timestamp() + duration_seconds

    # Bounded so workers pause (on put) if the inserter ever falls behind —
    # we never build a large backlog of stale alerts.
    queue: asyncio.Queue[tuple[dict[str, Any], bool]] = asyncio.Queue(
        maxsize=concurrency * 2
    )
    stop_workers = asyncio.Event()

    logger.info(
        "Cloudflare live generator started: duration=%ds, interval=%ds, "
        "poison=%.0f%%, concurrency=%d",
        duration_seconds,
        interval_seconds,
        poison_ratio * 100,
        concurrency,
    )

    async def _worker(worker_id: int) -> None:
        """Continuously generate alerts into the queue until stopped."""
        while not stop_workers.is_set() and _state.active:
            if datetime.now(timezone.utc).timestamp() >= end_time:
                break
            should_poison = random.random() < poison_ratio
            try:
                alert_data = await asyncio.to_thread(
                    cloudflare.generate_alert,
                    inject_poison=should_poison,
                    require_live=True,
                )
            except asyncio.CancelledError:
                raise
            except CloudflareGenerationError as exc:
                _state.last_error = str(exc)
                logger.warning(
                    "Worker %d: Cloudflare generation failed — retrying: %s",
                    worker_id, exc,
                )
                await asyncio.sleep(0.5)
                continue
            except Exception:  # noqa: BLE001
                logger.exception("Worker %d: unexpected generation error", worker_id)
                await asyncio.sleep(0.5)
                continue
            await queue.put((alert_data, should_poison))

    workers = [asyncio.create_task(_worker(i)) for i in range(concurrency)]

    try:
        while _state.active and datetime.now(timezone.utc).timestamp() < end_time:
            # Wait for the next pre-generated alert.  The timeout only fires if
            # every worker is stuck (rate-limited/slow), so a single bad call
            # never kills the run — we skip the tick and keep the feed alive.
            try:
                alert_data, should_poison = await asyncio.wait_for(
                    queue.get(), timeout=interval_seconds + 10
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "No alert ready within %ds — skipping this tick",
                    interval_seconds + 10,
                )
                continue

            # Time the insert separately from the queue wait so a slow ramp-up
            # (first call) does not compress the spacing between later alerts.
            insert_start = time.monotonic()
            try:
                if should_poison:
                    _state.poison_injected += 1

                # Run the firewall (same code path as POST /alerts/)
                flags = check_alert(
                    source_alert_id=alert_data["source_alert_id"],
                    alert_type=alert_data["alert_type"],
                    raw_payload=alert_data["raw_payload"],
                )

                if flags:
                    _state.firewall_caught += 1

                # Insert alert into Supabase (blocking call kept off the loop)
                alert_row = {
                    "source_alert_id": alert_data["source_alert_id"],
                    "alert_type": alert_data["alert_type"],
                    "raw_payload": alert_data["raw_payload"],
                    "status": "pending",
                }
                result = await asyncio.to_thread(
                    supabase.table("alerts").insert(alert_row).execute
                )

                if result.data:
                    alert_id = result.data[0]["id"]
                    _state.alerts_generated += 1

                    # Write firewall flags if any
                    if flags:
                        raw_json = json.dumps(
                            alert_data["raw_payload"], ensure_ascii=False
                        )
                        flag_rows = [
                            {
                                "alert_id": alert_id,
                                "flag_reason": reason,
                                "raw_snippet": sanitize_snippet(raw_json),
                            }
                            for reason in flags
                        ]
                        await asyncio.to_thread(
                            supabase.table("firewall_flags").insert(flag_rows).execute
                        )

                    logger.info(
                        "Alert %s [%s] inserted (poison=%s, flagged=%d)",
                        alert_data["source_alert_id"],
                        alert_data["alert_type"],
                        should_poison,
                        len(flags),
                    )
                else:
                    logger.warning("Failed to insert alert into Supabase")

            except asyncio.CancelledError:
                raise  # Let the cancellation propagate
            except Exception:  # noqa: BLE001
                logger.exception("Error inserting alert")

            # Sleep only the remainder of the interval so the cadence between
            # inserts stays ~interval seconds (a new alert every ~3s).
            elapsed = time.monotonic() - insert_start
            remainder = max(0.0, interval_seconds - elapsed)
            if remainder:
                await asyncio.sleep(remainder)

    except asyncio.CancelledError:
        logger.info("Generator stopped (cancelled)")
    finally:
        stop_workers.set()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        _state.active = False
        logger.info(
            "Generator finished: %d alerts generated, %d poison, %d caught by firewall",
            _state.alerts_generated,
            _state.poison_injected,
            _state.firewall_caught,
        )
