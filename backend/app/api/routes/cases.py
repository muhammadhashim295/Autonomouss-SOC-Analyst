"""Phase 13 — Cases API: analyst decisions + case detail.

- ``POST /cases/{case_id}/decision`` — approve / redirect / self-act
- ``GET  /cases/{case_id}``         — full case detail (case + alert +
  overrides + firewall flags + memory record) for the escalation screen
  and the Phase 15 case-detail view
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.services.analyst_decisions import DecisionError, apply_analyst_decision

router = APIRouter(prefix="/cases", tags=["cases"])


class AnalystDecisionRequest(BaseModel):
    """Body for POST /cases/{case_id}/decision."""

    decision: Literal["approved", "redirected", "self_acted"]
    analyst_action: Optional[str] = None
    analyst_reasoning: Optional[str] = None


@router.get("/")
async def list_cases(
    status: Optional[str] = Query(None, description="Filter by action_status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """List investigation cases, optionally filtered by action_status. Newest first."""
    supabase = get_supabase()
    query = (
        supabase.table("cases")
        .select("*, alerts:alert_id(id, source_alert_id, alert_type, raw_payload, received_at, status)")
        .order("closed_at", desc=True)
        .order("id", desc=True)
    )
    if status:
        query = query.eq("action_status", status)
    result = query.range(offset, offset + limit - 1).execute()
    return result.data or []


@router.post("/{case_id}/decision")
async def submit_decision(
    case_id: str,
    request: AnalystDecisionRequest,
) -> dict[str, Any]:
    """Record an analyst decision on a paused/escalated case.

    - ``approved``: execute the suggested action (simulated), close the case
    - ``redirected``: the analyst chose a different action — requires
      ``analyst_action``; logged as a correction memory record
    - ``self_acted``: the analyst handled it manually — requires
      ``analyst_action``; logged as a correction memory record

    Closes the case, writes the analyst_overrides row, and performs the
    deferred memory write (corrections are retrieved with boosted priority
    for similar future alerts).
    """
    try:
        return apply_analyst_decision(
            case_id=case_id,
            decision=request.decision,
            analyst_action=request.analyst_action,
            analyst_reasoning=request.analyst_reasoning,
        )
    except DecisionError as exc:
        # Distinguish not-found from invalid-state for the client
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=422, detail=message) from exc


@router.get("/{case_id}")
async def get_case(case_id: str) -> dict[str, Any]:
    """Full case detail — everything the escalation/case screen needs.

    Returns the case row (with parsed investigation snapshot), the alert,
    any analyst overrides, firewall flags on the alert, and the memory
    record written for this case.
    """
    supabase = get_supabase()

    case_rows = supabase.table("cases").select("*").eq("id", case_id).limit(1).execute()
    if not case_rows.data:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    case = case_rows.data[0]

    alert = None
    if case.get("alert_id"):
        alert_rows = (
            supabase.table("alerts").select("*")
            .eq("id", case["alert_id"]).limit(1).execute()
        )
        alert = alert_rows.data[0] if alert_rows.data else None

    overrides = (
        supabase.table("analyst_overrides").select("*")
        .eq("case_id", case_id).order("created_at", desc=True).execute()
    ).data or []

    firewall_flags = []
    if alert:
        firewall_flags = (
            supabase.table("firewall_flags").select("*")
            .eq("alert_id", alert["id"]).execute()
        ).data or []

    memory_record = None
    if case.get("qoder_memory_record_id"):
        mem_rows = (
            supabase.table("memory_records").select("*")
            .eq("id", case["qoder_memory_record_id"]).limit(1).execute()
        )
        if mem_rows.data:
            memory_record = mem_rows.data[0]

    # Parse the stored action JSON for convenience
    action_taken = None
    if case.get("action_taken"):
        try:
            action_taken = json.loads(case["action_taken"])
        except (json.JSONDecodeError, TypeError):
            action_taken = {"raw": case["action_taken"]}

    return {
        "case": {**case, "action_taken_parsed": action_taken},
        "alert": alert,
        "analyst_overrides": overrides,
        "firewall_flags": firewall_flags,
        "memory_record": memory_record,
    }
