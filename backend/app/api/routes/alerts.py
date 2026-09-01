"""Alert ingestion endpoints — POST to ingest, GET to list, enrich, triage."""

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.firewall import check_alert, sanitize_snippet
from app.db.supabase_client import get_supabase
from app.models.schemas import AlertCreate, AlertResponse, ReinvestigateRequest
from app.services.actions import decide_and_execute_action
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


@router.post("/{alert_id}/reinvestigate")
async def reinvestigate_alert(
    alert_id: str,
    request: ReinvestigateRequest | None = None,
) -> dict[str, Any]:
    """Trigger the Secondary Agent to independently re-investigate an alert.

    Phase 8 dual-agent cross-check flow + Phase 10 action pipeline:
    1. Looks up the alert
    2. Obtains the Primary Agent's report — either from the request body,
       or by running the Primary Agent first
    3. Sends alert + primary's report to the Deep Investigation Agent,
       which re-derives the evidence independently
    4. Updates the existing case with the secondary verdict
    5. Decides and (if allowed) executes the response action — enforced
       logic: standard actions execute autonomously in agentic mode when
       confident, high-impact actions always await analyst approval
    6. Returns both agents' results plus the action outcome
    """
    client = get_supabase()

    # 1. Look up the alert
    result = client.table("alerts").select("*").eq("id", alert_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = result.data[0]
    qoder = get_qoder_client()

    # 2. Obtain the primary agent's investigation result
    primary_ran_now = False
    if request and request.primary_report:
        # Primary report supplied by the caller (e.g. chained after /triage)
        primary_result: dict[str, Any] = {
            "agent_response": request.primary_report,
            "parsed": {
                "verdict": request.primary_verdict or "unknown",
                "confidence": request.primary_confidence or 0.5,
            },
        }
        case = _get_or_create_case(client, alert_id, alert, primary_result)
    else:
        # No report supplied — run the Primary Agent first
        try:
            client.table("alerts").update({"status": "in_review"}).eq("id", alert_id).execute()
            primary_result = qoder.triage_alert(alert)
            primary_ran_now = True
        except QoderClientError as exc:
            client.table("alerts").update({"status": "pending"}).eq("id", alert_id).execute()
            raise HTTPException(status_code=502, detail=f"Primary agent error: {exc}")

        try:
            case = persist_case(
                alert_id=alert_id,
                parsed=primary_result["parsed"],
                enrichment=primary_result["enrichment"],
                impact_level=primary_result["impact_level"],
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=f"Case persistence error: {exc}")

    # 3. Run the Secondary Agent's independent re-investigation
    try:
        secondary_result = qoder.reinvestigate_alert(alert, primary_result)
    except QoderClientError as exc:
        raise HTTPException(status_code=502, detail=f"Secondary agent error: {exc}")

    # 4. Update the case with the secondary verdict
    secondary_verdict = secondary_result["parsed"].get("secondary_verdict")
    update_fields: dict[str, Any] = {}
    if secondary_verdict:
        update_fields["secondary_verdict"] = secondary_verdict
    if update_fields:
        client.table("cases").update(update_fields).eq("id", case["id"]).execute()

    # 5. Phase 10 action pipeline — decide + execute (simulated) the action
    #    based on the cross-checked verdict.  Enforced logic in
    #    app/services/actions.py, never LLM discretion.
    action_outcome = decide_and_execute_action(
        alert=alert,
        case=case,
        primary_parsed=primary_result["parsed"],
        secondary_parsed=secondary_result["parsed"],
        enrichment=secondary_result.get("enrichment"),
    )

    # 6. Return both agents' results + the action outcome
    return {
        "alert_id": alert_id,
        "source_alert_id": alert.get("source_alert_id"),
        "case_id": case["id"],
        "primary_ran_now": primary_ran_now,
        "primary": {
            "verdict": primary_result["parsed"].get("verdict"),
            "confidence": primary_result["parsed"].get("confidence"),
            "agent_response": primary_result["agent_response"],
        },
        "secondary": {
            "verdict": secondary_verdict,
            "confidence": secondary_result["parsed"].get("confidence"),
            "impact_level": secondary_result["parsed"].get("impact_level"),
            "reasoning": secondary_result["parsed"].get("reasoning", ""),
            "self_audit": secondary_result["parsed"].get("self_audit", ""),
            "agent_response": secondary_result["agent_response"],
            "session_id": secondary_result["session_id"],
        },
        "secondary_verdict": secondary_verdict,
        "action": {
            "action_id": action_outcome["decision"]["action_id"],
            "action_class": action_outcome["decision"]["action_class"],
            "action_status": action_outcome["decision"]["action_status"],
            "target": action_outcome["decision"].get("target"),
            "rationale": action_outcome["decision"].get("rationale"),
            "executed": action_outcome["decision"]["execute"],
            "record": action_outcome["record"],
            "case_closed": action_outcome["case_closed"],
            "alert_status": action_outcome["alert_status"],
        },
    }


def _get_or_create_case(
    client: Any,
    alert_id: str,
    alert: dict[str, Any],
    primary_result: dict[str, Any],
) -> dict[str, Any]:
    """Return the existing case for an alert, or create one from the
    primary result if none exists yet."""
    existing = (
        client.table("cases")
        .select("*")
        .eq("alert_id", alert_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    from app.services.investigation import classify_impact

    return persist_case(
        alert_id=alert_id,
        parsed=primary_result["parsed"],
        enrichment=primary_result.get("enrichment", {}),
        impact_level=classify_impact(
            alert.get("alert_type", "unknown"), alert.get("raw_payload", {})
        ),
    )
