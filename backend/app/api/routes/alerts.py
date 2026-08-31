"""Alert ingestion endpoints — POST to ingest, GET to list, enrich, triage."""

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.firewall import check_alert, sanitize_snippet
from app.db.supabase_client import get_supabase
from app.models.schemas import AlertCreate, AlertResponse
from app.services.investigation import persist_case
from app.services.qoder_client import QoderClientError, get_qoder_client
from app.services.skills import (
    correlate_logs,
    detect_deviation,
    enrich_iocs,
    map_attack_techniques,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/", response_model=AlertResponse, status_code=201)
async def ingest_alert(alert: AlertCreate) -> AlertResponse:
    """Ingest a new alert into the system.

    The log-poisoning **firewall** runs first (real code, not prompt-level).
    Flagged alerts are **never dropped** — they are always inserted into
    ``alerts`` *and* recorded in ``firewall_flags``.
    """
    client = get_supabase()

    # 1. Firewall — scan before any agent would see this
    flags = check_alert(
        source_alert_id=alert.source_alert_id,
        alert_type=alert.alert_type,
        raw_payload=alert.raw_payload,
    )

    # 2. Insert alert (always, even if flagged)
    data = alert.model_dump(mode="json")
    result = client.table("alerts").insert(data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert alert")

    inserted = result.data[0]
    alert_id = inserted["id"]

    # 3. Write firewall flags (if any)
    if flags:
        raw_json = json.dumps(alert.raw_payload, ensure_ascii=False)
        flag_rows = [
            {
                "alert_id": alert_id,
                "flag_reason": reason,
                "raw_snippet": sanitize_snippet(raw_json),
            }
            for reason in flags
        ]
        client.table("firewall_flags").insert(flag_rows).execute()

    return AlertResponse(**inserted)


@router.get("/", response_model=list[AlertResponse])
async def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status: pending, in_review, closed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[AlertResponse]:
    """List alerts, optionally filtered by status.  Newest first."""
    client = get_supabase()

    query = client.table("alerts").select("*").order("received_at", desc=True)

    if status:
        query = query.eq("status", status)

    result = query.range(offset, offset + limit - 1).execute()

    return [AlertResponse(**row) for row in result.data]


@router.get("/firewall-flags")
async def list_firewall_flags(
    alert_id: Optional[str] = Query(None, description="Filter by alert UUID"),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """List firewall flags.  Useful for the dashboard and for testing."""
    client = get_supabase()

    query = client.table("firewall_flags").select("*").order("created_at", desc=True)

    if alert_id:
        query = query.eq("alert_id", alert_id)

    result = query.limit(limit).execute()
    return result.data


@router.get("/{alert_id}/enrich")
async def enrich_alert(alert_id: str) -> dict[str, Any]:
    """Run all 4 investigation skills on an alert and return enrichment data.

    Skills: OTX IOC enrichment, ATT&CK mapping, log correlation,
    behavioral-deviation heuristic.
    """
    client = get_supabase()

    result = client.table("alerts").select("*").eq("id", alert_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = result.data[0]
    alert_type = alert.get("alert_type", "unknown")
    payload = alert.get("raw_payload", {})

    return {
        "alert_id": alert_id,
        "source_alert_id": alert.get("source_alert_id"),
        "otx_enrichment": enrich_iocs(payload),
        "attack_mapping": map_attack_techniques(alert_type, payload),
        "log_correlation": correlate_logs(alert_type, payload),
        "behavioral_deviation": detect_deviation(alert_type, payload),
    }


@router.post("/{alert_id}/triage")
async def triage_alert(alert_id: str) -> dict[str, Any]:
    """Trigger the Primary Agent to investigate a specific alert.

    Phase 7 full investigation flow:
    1. Retrieves similar past cases (stub — Phase 11)
    2. Runs all 4 investigation skills
    3. Sends structured prompt to the Qoder agent
    4. Parses the agent's response (verdict, confidence, reasoning, self-audit)
    5. Classifies impact level
    6. Persists the case to the ``cases`` table
    7. Returns the full case record
    """
    client = get_supabase()

    # 1. Look up the alert
    result = client.table("alerts").select("*").eq("id", alert_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = result.data[0]

    # 2. Update status to in_review
    client.table("alerts").update({"status": "in_review"}).eq("id", alert_id).execute()

    # 3. Call Qoder agent (full investigation flow)
    try:
        qoder = get_qoder_client()
        triage_result = qoder.triage_alert(alert)
    except QoderClientError as exc:
        # Revert status on failure
        client.table("alerts").update({"status": "pending"}).eq("id", alert_id).execute()
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}")

    # 4. Persist case to Supabase
    try:
        case = persist_case(
            alert_id=alert_id,
            parsed=triage_result["parsed"],
            enrichment=triage_result["enrichment"],
            impact_level=triage_result["impact_level"],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Case persistence error: {exc}")

    # 5. Update alert status to closed (primary investigation complete)
    client.table("alerts").update({"status": "closed"}).eq("id", alert_id).execute()

    return {
        "alert_id": alert_id,
        "source_alert_id": alert.get("source_alert_id"),
        "case_id": case["id"],
        "verdict": case["primary_verdict"],
        "confidence": case["primary_confidence"],
        "attack_technique": case.get("attack_technique"),
        "impact_level": case["impact_level"],
        "reasoning": case.get("reasoning", ""),
        "self_audit": case.get("self_audit", ""),
        "agent_response": triage_result["agent_response"],
        "enrichment": triage_result["enrichment"],
        "session_id": triage_result["session_id"],
    }
