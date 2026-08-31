"""Background alert generator — Gemini-backed live feed for demo/testing.

Runs as an asyncio task, generating alerts at a configurable interval.
Poison alerts (~15% by default) exercise the firewall continuously.
Generated alerts flow through the same ingestion path as manual alerts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.core.firewall import check_alert, sanitize_snippet
from app.db.supabase_client import get_supabase
from app.services.gemini_client import GeminiClient

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
        self.interval_seconds: int = 5
        self.poison_ratio: float = 0.15
        self._task: Optional[asyncio.Task[None]] = None

    def to_status_dict(self) -> dict[str, Any]:
        """Return the current state as a JSON-serialisable dict."""
        if not self.active:
            return {"status": "idle"}

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
        }


# Module-level singleton
_state = _GeneratorState()


def get_generator_status() -> dict[str, Any]:
    """Return the current generator status."""
    return _state.to_status_dict()


def start_generation(
    duration_seconds: int = 120,
    interval_seconds: int = 5,
    poison_ratio: float = 0.15,
) -> dict[str, Any]:
    """Start a new alert generation run.

    Returns the run details.  The actual generation happens in an
    asyncio background task — this function returns immediately.
    """
    if _state.active:
        raise RuntimeError("A generation run is already active")

    run_id = str(uuid4())[:8]
    total_planned = max(1, duration_seconds // interval_seconds)

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
    """Async loop that generates alerts on each interval tick.

    Runs as an asyncio.Task.  On each tick:
    1. Asks the GeminiClient to generate one alert (with optional poison)
    2. Runs the firewall check on the payload
    3. Inserts the alert into Supabase (always)
    4. Inserts firewall_flags if the firewall caught something
    """
    import random

    gemini = GeminiClient()
    supabase = get_supabase()
    end_time = datetime.now(timezone.utc).timestamp() + duration_seconds

    logger.info(
        "Generator started: duration=%ds, interval=%ds, poison=%.0f%%, gemini=%s",
        duration_seconds,
        interval_seconds,
        poison_ratio * 100,
        "available" if gemini.available else "template-only",
    )

    try:
        while _state.active and datetime.now(timezone.utc).timestamp() < end_time:
            try:
                # Decide whether this tick should be poisoned
                should_poison = random.random() < poison_ratio

                # Generate one alert
                alert_data = gemini.generate_alert(inject_poison=should_poison)

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

                # Insert alert into Supabase
                alert_row = {
                    "source_alert_id": alert_data["source_alert_id"],
                    "alert_type": alert_data["alert_type"],
                    "raw_payload": alert_data["raw_payload"],
                    "status": "pending",
                }
                result = supabase.table("alerts").insert(alert_row).execute()

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
                        supabase.table("firewall_flags").insert(flag_rows).execute()

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
                logger.exception("Error generating/inserting alert")

            # Sleep until next tick (or until cancelled)
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                raise

    except asyncio.CancelledError:
        logger.info("Generator stopped (cancelled)")
    finally:
        _state.active = False
        logger.info(
            "Generator finished: %d alerts generated, %d poison, %d caught by firewall",
            _state.alerts_generated,
            _state.poison_injected,
            _state.firewall_caught,
        )
