"""Live feed generation endpoints — start, status, stop."""

from fastapi import APIRouter, HTTPException

from app.services.alert_generator import (
    get_generator_status,
    start_generation,
    stop_generation,
)
from app.services.cloudflare_client import CloudflareGenerationError

router = APIRouter(prefix="/alerts/generate", tags=["generate"])


@router.post("/start")
async def generate_start(
    duration_seconds: int = 120,
    interval_seconds: int = 3,
    poison_ratio: float = 0.15,
) -> dict:
    """Start a Cloudflare Workers AI-backed alert generation run.

    The generation runs as a background task — this endpoint returns
    immediately.  Generated alerts flow through the normal ingestion
    pipeline including the log-poisoning firewall.

    - **duration_seconds**: how long the run lasts (default 120)
    - **interval_seconds**: seconds between each alert (default 3 — the stable
      point of the 2-3s live-feed window)
    - **poison_ratio**: probability of injecting a poison payload per tick (default 0.15 ≈ 1 in 7)
    """
    if not (2 <= interval_seconds <= 300):
        raise HTTPException(
            status_code=400,
            detail="interval_seconds must be between 2 and 300",
        )
    if not (0.0 <= poison_ratio <= 1.0):
        raise HTTPException(
            status_code=400,
            detail="poison_ratio must be between 0.0 and 1.0",
        )
    if not (10 <= duration_seconds <= 3600):
        raise HTTPException(
            status_code=400,
            detail="duration_seconds must be between 10 and 3600",
        )

    try:
        return start_generation(duration_seconds, interval_seconds, poison_ratio)
    except CloudflareGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/status")
async def generate_status() -> dict:
    """Check whether a generation run is currently active."""
    return get_generator_status()


@router.post("/stop")
async def generate_stop() -> dict:
    """Cancel an in-progress generation run early."""
    try:
        return stop_generation()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
