"""Phase 10 — Standard vs high-impact action catalog + simulated executor.

Per design.md, action gating is **enforced logic** — a lookup against a
config-driven catalog — never a judgment call left to the LLM's discretion.

Standard / low-impact (secondary agent may act autonomously in agentic mode):
- ``block_ip``         Block a single known-malicious IP/domain (OTX-flagged IOC)
- ``open_ticket``      Open a ticket for analyst review
- ``flag_for_review``  Flag/tag an alert for review (no system change)
- ``enrich_document``  Enrich and document only (no system change)

High-impact (always human-gated, regardless of mode):
- ``isolate_host``     Isolate a host from the network
- ``disable_account``  Disable/lock a user account
- Any action touching a tagged critical asset, or affecting more than
  one asset at once, is high-impact — enforced upstream by
  :func:`app.services.investigation.classify_impact`.

Execution is **simulated** (this is a demo framework — no real firewalls or
identity providers are touched), but every execution produces a structured,
auditable log record that is persisted on the case row.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ── Action catalog (config-driven — the lookup list design.md requires) ──────

STANDARD_ACTIONS: dict[str, dict[str, str]] = {
    "block_ip": {
        "name": "Block malicious IOC",
        "description": "Block a single known-malicious IP/domain (OTX-flagged IOC)",
        "system_change": "yes",
    },
    "open_ticket": {
        "name": "Open investigation ticket",
        "description": "Open a ticket for analyst review",
        "system_change": "yes",
    },
    "flag_for_review": {
        "name": "Flag for analyst review",
        "description": "Flag/tag the alert for review (no system change)",
        "system_change": "no",
    },
    "enrich_document": {
        "name": "Enrich and document",
        "description": "Enrich and document only (no system change)",
        "system_change": "no",
    },
}

HIGH_IMPACT_ACTIONS: dict[str, dict[str, str]] = {
    "isolate_host": {
        "name": "Isolate host from network",
        "description": "Network-isolate the affected host (requires analyst approval)",
    },
    "disable_account": {
        "name": "Disable user account",
        "description": "Disable/lock the targeted user account (requires analyst approval)",
    },
}

# Alert types where the natural high-impact response targets an account
# rather than a host (credential-access attacks).
_ACCOUNT_TARGETED_TYPES = {"brute_force_login", "authentication_failure"}


# ── Decision logic (enforced — the "skill" the secondary agent calls) ────────


def _effective_verdict(
    primary_verdict: Optional[str],
    secondary_verdict: Optional[str],
) -> tuple[Optional[str], bool]:
    """Resolve the cross-checked verdict from both agents.

    Returns ``(verdict, agents_agree)``.  ``disagree`` resolves to
    ``(None, False)`` — escalation territory, no autonomous action.
    A missing secondary verdict defers to the primary but is not treated
    as agreement.
    """
    if secondary_verdict == "disagree":
        return None, False
    if secondary_verdict in ("false_positive", "true_positive"):
        if primary_verdict and secondary_verdict != primary_verdict:
            return None, False
        return secondary_verdict, secondary_verdict == primary_verdict
    if secondary_verdict == "agree":
        return primary_verdict, True
    # No secondary signal — trust the primary's verdict but note the gap
    return primary_verdict, False


def _pick_otx_flagged_target(enrichment: dict[str, Any]) -> Optional[str]:
    """Return the first OTX-flagged malicious IOC (IP or domain), if any.

    An IOC qualifies as 'known-malicious' when OTX reports it
    malware-associated or with a low reputation score (< 50).
    At most ONE target is returned — blocking is a single-IOC action.
    """
    otx = enrichment.get("otx_enrichment", {}) if enrichment else {}

    for ip_r in otx.get("ip_results", []):
        if ip_r.get("malware"):
            return ip_r.get("ip")
        rep = ip_r.get("reputation")
        if isinstance(rep, (int, float)) and 0 < rep < 50:
            return ip_r.get("ip")

    for dom_r in otx.get("domain_results", []):
        rep = dom_r.get("reputation")
        if isinstance(rep, (int, float)) and 0 < rep < 50:
            return dom_r.get("domain")

    return None


def _pick_high_impact_action(alert_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Rule-based selection of the *suggested* high-impact action."""
    if alert_type in _ACCOUNT_TARGETED_TYPES:
        return {
            "action_id": "disable_account",
            "target": payload.get("user") or payload.get("target_user") or "unknown",
        }
    return {
        "action_id": "isolate_host",
        "target": payload.get("hostname") or payload.get("source_ip") or "unknown",
    }


def decide_action(
    *,
    primary_verdict: Optional[str],
    secondary_verdict: Optional[str],
    secondary_confidence: Optional[float],
    impact_level: str,
    alert_type: str,
    payload: dict[str, Any],
    enrichment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Decide what action to take after the secondary agent's cross-check.

    Enforced fixed flow (no mode toggle):
    1. Secondary disagrees or concludes false_positive -> close + document
    2. Primary was false_positive -> close + document
    3. Both agree on true_positive:
       - high_impact -> ALWAYS human-gated (awaiting_approval)
       - standard / low-impact -> ALWAYS autonomous execution (executed)
    """
    confidence = secondary_confidence if secondary_confidence is not None else 0.5
    threshold = settings.action_confidence_threshold

    # 1. Secondary disagrees with primary -> close and document
    if secondary_verdict in ("false_positive", "disagree"):
        return {
            "action_id": None,
            "action_class": None,
            "execute": False,
            "action_status": "none",
            "target": None,
            "rationale": (
                f"Secondary agent concluded false_positive / disagreed with primary "
                f"(primary={primary_verdict}, secondary={secondary_verdict}); "
                "case closed with no action."
            ),
        }

    # 2. Primary false positive -> close, no action
    if primary_verdict == "false_positive":
        return {
            "action_id": None,
            "action_class": None,
            "execute": False,
            "action_status": "none",
            "target": None,
            "rationale": (
                f"Primary verdict false_positive; case closed with no action."
            ),
        }

    # 3. True positive confirmed
    # 3a. High-impact -> ALWAYS human-gated
    if impact_level == "high_impact":
        suggested = _pick_high_impact_action(alert_type, payload)
        return {
            "action_id": suggested["action_id"],
            "action_class": "high_impact",
            "execute": False,
            "action_status": "awaiting_approval",
            "target": suggested["target"],
            "rationale": (
                f"Impact classification is high_impact (enforced logic); "
                f"suggested action {suggested['action_id']} requires analyst "
                "approval."
            ),
        }

    # 3b. Standard / low-impact -> ALWAYS autonomous execution
    target = _pick_otx_flagged_target(enrichment or {})
    if target:
        return {
            "action_id": "block_ip",
            "action_class": "standard",
            "execute": True,
            "action_status": "executed",
            "target": target,
            "rationale": (
                f"Cross-checked true_positive: OTX-flagged IOC {target} blocked "
                "(single-IOC standard action executed autonomously)."
            ),
        }

    return {
        "action_id": "open_ticket",
        "action_class": "standard",
        "execute": True,
        "action_status": "executed",
        "target": alert_type,
        "rationale": (
            "Cross-checked true_positive: standard action open_ticket "
            "executed autonomously."
        ),
    }


# ── Simulated execution ─────────────────────────────────────────────────────


def execute_action(
    decision: dict[str, Any],
    *,
    alert: dict[str, Any],
    case_id: str,
) -> dict[str, Any]:
    """Simulate executing the decided action and build the audit record.

    Returns a structured log entry: what ran, against what target, when,
    with what result — this is the 'logged, documented action' that ends
    up in ``cases.action_taken``.
    """
    action_id = decision["action_id"]
    now = datetime.now(timezone.utc)

    record: dict[str, Any] = {
        "action": action_id,
        "action_name": (
            STANDARD_ACTIONS.get(action_id, {}).get("name")
            or HIGH_IMPACT_ACTIONS.get(action_id, {}).get("name")
            or action_id
        ),
        "target": decision.get("target"),
        "executed_at": now.isoformat(),
        "simulated": True,
        "case_id": case_id,
        "source_alert_id": alert.get("source_alert_id"),
    }

    if not decision["execute"]:
        # Not executed — record the suggestion awaiting human decision
        record["result"] = "not_executed"
        record["reason"] = decision["rationale"]
        return record

    # Simulated outcomes per action type
    if action_id == "block_ip":
        record["result"] = "blocked"
        record["details"] = (
            f"IOC {decision.get('target')} added to perimeter blocklist "
            "(simulated) — single-IOC standard action"
        )
    elif action_id == "open_ticket":
        ticket_ref = f"SOC-{now.strftime('%Y%m%d')}-{case_id[:8].upper()}"
        record["result"] = "ticket_opened"
        record["ticket_ref"] = ticket_ref
        record["details"] = f"Investigation ticket {ticket_ref} created (simulated)"
    elif action_id == "flag_for_review":
        record["result"] = "flagged"
        record["details"] = "Alert tagged for analyst review (no system change)"
    elif action_id == "enrich_document":
        record["result"] = "documented"
        record["details"] = "Enrichment results documented on the case (no system change)"
    else:
        record["result"] = "unknown_action"
        record["details"] = f"No executor defined for {action_id}"

    record["reason"] = decision["rationale"]
    return record


# ── Orchestration: decide → execute → persist on the case ───────────────────


def decide_and_execute_action(
    *,
    alert: dict[str, Any],
    case: dict[str, Any],
    primary_parsed: dict[str, Any],
    secondary_parsed: dict[str, Any],
    enrichment: Optional[dict[str, Any]] = None,
    primary_provider: str = "groq",
    secondary_provider: str = "groq",
) -> dict[str, Any]:
    """Run the action pipeline for a cross-checked case in the fixed flow.

    1. Decide the action (enforced rule cascade — never LLM discretion)
    2. Execute it if allowed (simulated) and build the audit record
    3. Persist ``action_taken`` / ``action_status`` / ``closed_at`` on the
       case row
    4. Update the alert status (closed vs in_review)

    Returns the action outcome dict for the API response.
    """
    supabase = get_supabase()

    alert_type = alert.get("alert_type", "unknown")
    payload = alert.get("raw_payload", {})

    decision = decide_action(
        primary_verdict=primary_parsed.get("verdict"),
        secondary_verdict=secondary_parsed.get("secondary_verdict"),
        secondary_confidence=secondary_parsed.get("confidence"),
        impact_level=case.get("impact_level", "standard"),
        alert_type=alert_type,
        payload=payload,
        enrichment=enrichment,
    )

    record = execute_action(decision, alert=alert, case_id=case["id"])

    # Persist on the case row.  A case closes when the action pipeline has
    # fully resolved (executed or no action needed); it stays open while a
    # human decision is pending.
    case_closed = decision["action_status"] in ("executed", "none")

    # Phase 13: snapshot the full investigation onto the case — the
    # deferred memory write at analyst-decision time (and the Phase 15
    # case-detail screen) need the parsed output + enrichment later.
    investigation_snapshot = {
        "primary_parsed": {
            k: primary_parsed.get(k)
            for k in ("verdict", "confidence", "reasoning", "self_audit", "attack_technique")
        },
        "secondary_parsed": {
            k: secondary_parsed.get(k)
            for k in ("secondary_verdict", "confidence", "reasoning", "self_audit", "impact_level")
        },
        "enrichment": enrichment,
        # Provider provenance — always recorded here (JSONB) so it survives even
        # before migration 005 adds the dedicated cases columns.
        "primary_provider": primary_provider,
        "secondary_provider": secondary_provider,
    }

    update_fields: dict[str, Any] = {
        "action_status": decision["action_status"],
        "action_taken": json.dumps(record, indent=2) if record["action"] else None,
        "investigation_snapshot": investigation_snapshot,
    }
    if case_closed:
        update_fields["closed_at"] = datetime.now(timezone.utc).isoformat()

    supabase.table("cases").update(update_fields).eq("id", case["id"]).execute()

    # Phase 11: write the structured memory record on case close.
    # Must never break the closing flow — failures are logged, not raised.
    memory_record_id = None
    if case_closed:
        from app.services.memory_store import write_case_record

        memory_record_id = write_case_record(
            alert=alert,
            case={**case, "action_status": decision["action_status"]},
            primary_parsed=primary_parsed,
            enrichment=enrichment,
            action_record=record if record["action"] else None,
            secondary_parsed=secondary_parsed,
        )

    # Alert status mirrors the case state
    alert_status = "closed" if case_closed else "in_review"
    supabase.table("alerts").update({"status": alert_status}).eq(
        "id", alert["id"]
    ).execute()

    logger.info(
        "Case %s action pipeline: action=%s status=%s target=%s closed=%s",
        case["id"],
        decision["action_id"],
        decision["action_status"],
        decision.get("target"),
        case_closed,
    )

    return {
        "decision": decision,
        "record": record,
        "case_closed": case_closed,
        "alert_status": alert_status,
        "memory_record_id": memory_record_id,
    }
