"""Phase 11 — Memory store API: retrieve RAG memory records.

- ``GET /memory/records`` — list memory records with optional type filter
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/records")
async def list_memory_records(
    record_type: Optional[str] = Query(None, description="Filter by record_type: case or correction"),
    alert_type: Optional[str] = Query(None, description="Filter by alert_type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """List RAG memory records, optionally filtered. Newest first."""
    supabase = get_supabase()
    query = (
        supabase.table("memory_records")
        .select("*, alerts:alert_id(id, source_alert_id, alert_type, raw_payload)")
        .order("created_at", desc=True)
    )
    if record_type:
        query = query.eq("record_type", record_type)
    if alert_type:
        query = query.eq("alert_type", alert_type)
    result = query.range(offset, offset + limit - 1).execute()
    return result.data or []
