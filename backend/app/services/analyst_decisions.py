"""Phase 13 — Analyst decision handling + correction memory.

Handles the three analyst decisions on a paused/escalated case
(design.md escalation screen):

- ``approved``    — analyst endorses the suggested action; it executes
                    (simulated) and the case closes as a normal case record
- ``redirected``  — analyst chooses a different action; the redirect is
                    logged as a **correction** memory record
- ``self_acted``  — analyst handles it manually outside the framework;
                    logged as a **correction** memory record

Every decision writes an ``analyst_overrides`` row, closes the case,
and performs the memory write that the action pipeline deferred
(awaiting-approval cases do not write memory until the human decides —
the record should capture the FINAL outcome).

Correction records carry ``record_type='correction'`` and the
``analyst_correction`` text, and are retrieved with boosted priority
(Phase 11 scoring) so similar future alerts see the analyst's guidance.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_DECIDABLE_STATUSES = {"awaiting_approval", "escalated"}

# Simulated execution results for analyst-approved actions
_APPROVED_RESULTS = {
    "block_ip": "blocked",
    "open_ticket": "ticket_opened",
    "flag_for_review": "flagged",
    "enrich_document": "documented",
    "isolate_host": "isolated",
    "disable_account": "disabled",
}


class DecisionError(Exception):
    """Raised when an analyst decision cannot be applied to a case."""


def _analyst_action_record(
    decision: str,
    suggested: dict[str, Any],
    analyst_action: Optional[str],
    analyst_reasoning: Optional[str],
    case_id: str,
) -> dict[str, Any]:
    """Build the audit record for what the analyst actually did."""
    now = datetime.now(timezone.utc)
    suggested_id = suggested.get("action", "none")

    if decision == "approved":
        action_id = suggested_id
        result = _APPROVED_RESULTS.get(action_id, "executed")
        details = (
            f"Analyst approved the agents' suggested action '{action_id}' "
            f"on target '{suggested.get('target')}'; executed (simulated)."
        )
    elif decision == "redirected":
        action_id = analyst_action
        result = "redirected"
        details = (
            f"Analyst redirected from suggested '{suggested_id}' to: "
            f"{analyst_action}"
        )
    else:  # self_acted
        action_id = analyst_action
        result = "self_acted"
        details = f"Analyst handled manually outside the framework: {analyst_action}"

    return {
        "action": action_id,
        "action_name": f"analyst:{decision}",
        "target": suggested.get("target"),
        "mode": "analyst_decision",
        "executed_at": now.isoformat(),
        "simulated": True,
        "case_id": case_id,
        "result": result,
        "details": details,
        "reason": analyst_reasoning or "",
        "original_suggestion": suggested_id,
        "decided_by": "analyst",
    }


def apply_analyst_decision(
    *,
    case_id: str,
    decision: str,
    analyst_action: Optional[str] = None,
    analyst_reasoning: Optional[str] = None,
) -> dict[str, Any]:
    """Apply an analyst decision to a paused/escalated case.

    1. Validates the case is awaiting a decision
    2. Writes the ``analyst_overrides`` row
    3. Resolves the action per the decision (approve executes the
       suggestion; redirect/self-act record the analyst's choice)
    4. Closes the case and the alert
    5. Writes the deferred memory record — as a **correction** for
       redirected/self-acted decisions, a plain case record for approved

    Returns the resolution summary for the API response.
    """
    if decision not in ("approved", "redirected", "self_acted"):
        raise DecisionError(
            f"Invalid decision '{decision}' — must be approved, redirected, or self_acted"
        )
    if decision in ("redirected", "self_acted") and not analyst_action:
        raise DecisionError(
            f"Decision '{decision}' requires analyst_action text "
            "(what the analyst did instead)"
        )

    supabase = get_supabase()

    # 1. Load and validate the case
    case_rows = (
        supabase.table("cases").select("*").eq("id", case_id).limit(1).execute()
    )
    if not case_rows.data:
        raise DecisionError(f"Case {case_id} not found")
    case = case_rows.data[0]

    if case.get("action_status") not in _DECIDABLE_STATUSES:
        if case.get("status") == "closed" or case.get("action_status") in ("executed", "redirected", "self_acted"):
            logger.info("Case %s is already closed/executed (%s); returning existing record.", case_id, case.get("action_status"))
            return {
                "case_id": case_id,
                "status": case.get("status", "closed"),
                "action_status": case.get("action_status", "executed"),
                "case": case,
                "memory_record_id": case.get("qoder_memory_record_id"),
                "memory_record_type": "decision",
                "analyst_correction": None,
            }
        raise DecisionError(
            f"Case {case_id} is not awaiting a decision "
            f"(action_status={case.get('action_status')})"
        )


    # 2. Load the alert + investigation snapshot (persisted at pipeline time)
    alert_rows = (
        supabase.table("alerts").select("*").eq("id", case["alert_id"]).limit(1).execute()
    )
    if not alert_rows.data:
        raise DecisionError(f"Alert {case['alert_id']} for case {case_id} not found")
    alert = alert_rows.data[0]

    snapshot = case.get("investigation_snapshot") or {}
    primary_parsed = snapshot.get("primary_parsed", {})
    enrichment = snapshot.get("enrichment")

    suggested = (
        json.loads(case["action_taken"]) if case.get("action_taken") else {}
    )

    # 3. Write the analyst_overrides row (the audit trail of the override)
    org_id = case.get("org_id") or alert.get("org_id")
    override_row = {
        "case_id": case_id,
        "original_suggestion": suggested.get("action", "none"),
        "analyst_decision": decision,
        "analyst_action": analyst_action,
        "analyst_reasoning": analyst_reasoning,
    }
    if org_id:
        override_row["org_id"] = org_id

    try:
        override_result = (
            supabase.table("analyst_overrides").insert(override_row).execute()
        )
    except Exception as exc:
        logger.warning(
            "Insert analyst_overrides with org_id failed (%s); retrying without it.",
            exc,
        )
        override_row.pop("org_id", None)
        override_result = (
            supabase.table("analyst_overrides").insert(override_row).execute()
        )

    # 4. Resolve the action
    action_record = _analyst_action_record(
        decision, suggested, analyst_action, analyst_reasoning, case_id
    )

    if decision == "approved":
        action_status = "executed"
        record_type = "case"
        correction_text = None
    elif decision == "redirected":
        action_status = "executed"
        record_type = "correction"
        correction_text = (
            f"Agents suggested '{suggested.get('action', 'none')}' but the "
            f"analyst redirected to: {analyst_action}. "
            f"Reasoning: {analyst_reasoning or 'not stated'}. "
            f"Agent verdict had been {case.get('primary_verdict')} "
            f"(confidence {case.get('primary_confidence')})."
        )
    else:  # self_acted
        action_status = "none"
        record_type = "correction"
        correction_text = (
            f"Agents suggested '{suggested.get('action', 'none')}' but the "
            f"analyst self-acted: {analyst_action}. "
            f"Reasoning: {analyst_reasoning or 'not stated'}. "
            f"Agent verdict had been {case.get('primary_verdict')} "
            f"(confidence {case.get('primary_confidence')})."
        )

    # 5. Close the case + alert
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("cases").update(
        {
            "action_status": action_status,
            "action_taken": json.dumps(action_record, indent=2),
            "closed_at": now,
        }
    ).eq("id", case_id).execute()
    supabase.table("alerts").update({"status": "closed"}).eq(
        "id", case["alert_id"]
    ).execute()

    # 6. Deferred memory write — captures the FINAL outcome
    from app.services.memory_store import write_case_record

    secondary_parsed = snapshot.get("secondary_parsed")
    memory_record_id = write_case_record(
        alert=alert,
        case=case,
        primary_parsed=primary_parsed,
        enrichment=enrichment,
        action_record=action_record,
        secondary_parsed=secondary_parsed,
        record_type=record_type,
        analyst_correction=correction_text,
    )

    logger.info(
        "Analyst decision '%s' applied to case %s: action_status=%s, "
        "memory record type=%s (%s)",
        decision, case_id, action_status, record_type, memory_record_id,
    )

    return {
        "case_id": case_id,
        "alert_id": case["alert_id"],
        "source_alert_id": alert.get("source_alert_id"),
        "decision": decision,
        "action_status": action_status,
        "action_record": action_record,
        "memory_record_id": memory_record_id,
        "memory_record_type": record_type,
        "analyst_correction": correction_text,
        "override_id": (
            override_result.data[0]["id"] if override_result.data else None
        ),
        "case_closed": True,
    }
