"""Live event stream for the dual-agent investigation pipeline.

Runs the dual-agent investigation as an event generator yielding stages to
the client via Server-Sent Events (SSE).

2-Provider Architecture:
- **Groq** runs both the Primary Alert Triage Agent and the Secondary Deep
  Investigation Agent (``groq_client.py``)
- **Cloudflare Workers AI** generates live alerts (``cloudflare_client.py``)

Fixed Pipeline Flow:
1. Alert arrives -> firewall check.
2. If firewall flags alert -> escalate DIRECTLY to human analyst without
   running Primary or Secondary agents.
3. If clean -> Primary Agent investigates on Groq.
   - If false_positive -> close + document, no Secondary involvement.
   - If true_positive -> hand off to Secondary Agent.
4. Secondary Agent independently re-investigates on Groq.
   - If false_positive (disagrees with primary) -> close + document.
   - If true_positive (agrees):
     - low/standard impact -> execute autonomously (always autonomous, no mode check).
     - high impact -> ALWAYS escalate to human analyst (awaiting approval).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator

from app.core.firewall import check_alert, sanitize_snippet
from app.db.supabase_client import get_supabase
from app.services.actions import decide_and_execute_action
from app.services.groq_client import GroqClientError, get_groq_client
from app.services.investigation import (
    classify_impact,
    parse_agent_response,
    persist_case,
    retrieve_similar_cases,
)
from app.services.skills import (
    correlate_logs,
    detect_deviation,
    enrich_iocs,
    map_attack_techniques,
)

logger = logging.getLogger(__name__)


def _run_skills(alert_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run the 4 investigation skills fresh."""
    return {
        "otx_enrichment": enrich_iocs(payload),
        "attack_mapping": map_attack_techniques(alert_type, payload),
        "log_correlation": correlate_logs(alert_type, payload),
        "behavioral_deviation": detect_deviation(alert_type, payload),
    }


def run_dual_agent_stream(alert: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Stream investigation events for an alert following the fixed 2-provider flow."""
    alert_id = alert["id"]
    alert_type = alert.get("alert_type", "unknown")
    payload = alert.get("raw_payload", {})
    supabase = get_supabase()

    primary_client = get_groq_client()
    secondary_client = get_groq_client()
    primary_provider = "groq"
    secondary_provider = "groq"

    # ── Step 1: Firewall Check ──────────────────────────────────────────
    flags = check_alert(
        source_alert_id=alert.get("source_alert_id", ""),
        alert_type=alert_type,
        raw_payload=payload,
    )

    if flags:
        # Step 2: Escalate DIRECTLY to human analyst without running agents
        logger.warning(
            "Alert %s flagged by firewall (%s) — escalating directly to human analyst.",
            alert.get("source_alert_id"),
            flags,
        )

        raw_json = json.dumps(payload, ensure_ascii=False)
        flag_rows = [
            {
                "alert_id": alert_id,
                "flag_reason": reason,
                "raw_snippet": sanitize_snippet(raw_json),
                **({"org_id": alert.get("org_id")} if alert.get("org_id") else {}),
            }
            for reason in flags
        ]
        try:
            supabase.table("firewall_flags").insert(flag_rows).execute()
        except Exception:
            for f in flag_rows:
                f.pop("org_id", None)
            supabase.table("firewall_flags").insert(flag_rows).execute()

        yield {
            "event": "investigation_started",
            "data": {
                "alert_id": alert_id,
                "source_alert_id": alert.get("source_alert_id"),
                "alert_type": alert_type,
                "primary_provider": "firewall",
                "secondary_provider": None,
                "firewall_flags": flags,
            },
        }

        # Persist direct-escalation case
        now_iso = datetime.now(timezone.utc).isoformat()
        action_record = {
            "action": "flag_for_review",
            "action_name": "Firewall Poison Quarantine",
            "target": alert.get("source_alert_id"),
            "result": "escalated_to_analyst",
            "reason": f"Firewall flagged alert: {'; '.join(flags)}. Escalated directly to human analyst without agent investigation.",
            "simulated": True,
            "flags": flags,
            "executed_at": now_iso,
        }

        # Check if case was already created during ingestion
        existing_case = supabase.table("cases").select("id").eq("alert_id", alert_id).limit(1).execute()
        if existing_case.data:
            case_id = existing_case.data[0]["id"]
        else:
            case_row = {
                "alert_id": alert_id,
                "mode": "agentic",
                "primary_verdict": "true_positive",
                "primary_confidence": 1.0,
                "attack_technique": None,
                "impact_level": "high_impact",
                "action_taken": json.dumps(action_record, indent=2),
                "action_status": "awaiting_approval",
                "closed_at": None,
                "primary_provider": "firewall",
                "secondary_provider": None,
            }
            if alert.get("org_id"):
                case_row["org_id"] = alert["org_id"]

            try:
                case_res = supabase.table("cases").insert(case_row).execute()
            except Exception:
                case_row.pop("org_id", None)
                case_res = supabase.table("cases").insert(case_row).execute()

            case_id = case_res.data[0]["id"] if case_res.data else "case-quarantine"

        supabase.table("alerts").update({"status": "in_review"}).eq("id", alert_id).execute()

        yield {
            "event": "case_persisted",
            "data": {"case_id": case_id},
        }

        yield {
            "event": "action_decided",
            "data": {
                "action_id": "flag_for_review",
                "action_class": "high_impact",
                "action_status": "awaiting_approval",
                "target": alert.get("source_alert_id"),
                "rationale": f"Firewall flagged adversarial content: {'; '.join(flags)}. Directly escalated to analyst.",
                "executed": False,
                "record": action_record,
            },
        }

        yield {
            "event": "investigation_complete",
            "data": {
                "alert_id": alert_id,
                "source_alert_id": alert.get("source_alert_id"),
                "case_id": case_id,
                "primary_verdict": "true_positive",
                "primary_confidence": 1.0,
                "primary_reasoning": f"Firewall flagged alert: {'; '.join(flags)}.",
                "secondary_verdict": None,
                "impact_level": "high_impact",
                "action_id": "flag_for_review",
                "action_status": "awaiting_approval",
                "case_closed": False,
                "alert_status": "in_review",
                "primary_provider": "firewall",
                "secondary_provider": None,
                "firewall_flags": flags,
            },
        }
        return

    # ── Step 3: Firewall passed -> Primary Agent (Groq) ─────────────────
    yield {
        "event": "investigation_started",
        "data": {
            "alert_id": alert_id,
            "source_alert_id": alert.get("source_alert_id"),
            "alert_type": alert_type,
            "primary_provider": primary_provider,
            "secondary_provider": secondary_provider,
        },
    }

    similar_cases = retrieve_similar_cases(
        alert_type,
        payload,
        exclude_source_alert_id=alert.get("source_alert_id"),
    )
    yield {
        "event": "memory_retrieved",
        "data": {"agent": "primary", "similar_cases": similar_cases},
    }

    enrichment = _run_skills(alert_type, payload)
    impact_level = classify_impact(alert_type, payload)
    yield {
        "event": "enrichment_complete",
        "data": {
            "agent": "primary",
            "enrichment": enrichment,
            "impact_level": impact_level,
        },
    }

    session = primary_client.create_session(agent_id="primary")
    session_id = session.get("id", session.get("session_id", ""))
    if not session_id:
        raise GroqClientError(f"No session ID in primary response: {session}")

    prompt = primary_client._build_investigation_prompt(
        alert, alert_type, payload, enrichment, similar_cases
    )
    primary_client.send_message(session_id, prompt)
    yield {
        "event": "agent_started",
        "data": {
            "agent": "primary",
            "session_id": session_id,
            "provider": primary_provider,
        },
    }

    primary_parts: list[str] = []
    for stream_event in primary_client.stream_session_events(session_id):
        if stream_event["type"] == "delta":
            primary_parts.append(stream_event["text"])
            yield {
                "event": "agent_delta",
                "data": {"agent": "primary", "text": stream_event["text"]},
            }

    primary_text = "".join(primary_parts).strip()
    primary_parsed = parse_agent_response(primary_text)
    primary_verdict = primary_parsed.get("verdict")
    logger.info(
        "[handoff] Primary Agent finished for %s: verdict=%s conf=%s "
        "reasoning_chars=%d — deciding Secondary dispatch.",
        alert.get("source_alert_id"),
        primary_verdict,
        primary_parsed.get("confidence"),
        len(primary_text),
    )
    yield {
        "event": "agent_complete",
        "data": {
            "agent": "primary",
            "provider": primary_provider,
            "verdict": primary_parsed.get("verdict"),
            "confidence": primary_parsed.get("confidence"),
            "reasoning": primary_parsed.get("reasoning", ""),
            "attack_technique": primary_parsed.get("attack_technique"),
        },
    }

    logger.info("[handoff] Persisting Primary case for %s...", alert.get("source_alert_id"))
    case = persist_case(
        alert_id=alert_id,
        parsed=primary_parsed,
        enrichment=enrichment,
        impact_level=impact_level,
        primary_provider=primary_provider,
        secondary_provider=None if primary_parsed.get("verdict") == "false_positive" else secondary_provider,
    )
    yield {"event": "case_persisted", "data": {"case_id": case["id"]}}

    # ── Branch: If Primary Verdict is False Positive -> Close + Document ──
    if primary_verdict == "false_positive":
        logger.info(
            "Alert %s triaged as false_positive by Primary Agent. Closing without Secondary handoff.",
            alert.get("source_alert_id"),
        )
        action_outcome = decide_and_execute_action(
            alert=alert,
            case=case,
            primary_parsed=primary_parsed,
            secondary_parsed={"secondary_verdict": "false_positive", "confidence": primary_parsed.get("confidence")},
            enrichment=enrichment,
            primary_provider=primary_provider,
            secondary_provider=secondary_provider,
        )
        decision = action_outcome["decision"]
        yield {
            "event": "action_decided",
            "data": {
                "action_id": decision["action_id"],
                "action_class": decision["action_class"],
                "action_status": decision["action_status"],
                "target": decision.get("target"),
                "rationale": decision.get("rationale"),
                "executed": decision["execute"],
                "record": action_outcome["record"],
            },
        }
        yield {
            "event": "investigation_complete",
            "data": {
                "alert_id": alert_id,
                "source_alert_id": alert.get("source_alert_id"),
                "case_id": case["id"],
                "primary_verdict": "false_positive",
                "primary_confidence": primary_parsed.get("confidence"),
                "primary_reasoning": primary_parsed.get("reasoning", ""),
                "secondary_verdict": None,
                "impact_level": impact_level,
                "action_id": None,
                "action_status": "none",
                "case_closed": True,
                "alert_status": "closed",
                "memory_record_id": action_outcome.get("memory_record_id"),
                "primary_provider": primary_provider,
                "secondary_provider": None,
            },
        }
        return

    # ── Step 4: True Positive -> Secondary Agent (Groq) ───────────────────
    logger.info(
        "[handoff] Primary verdict=%s for %s — dispatching Secondary Deep "
        "Investigation Agent.",
        primary_verdict,
        alert.get("source_alert_id"),
    )
    primary_result = {
        "agent_response": primary_text,
        "parsed": primary_parsed,
        "enrichment": enrichment,
        "impact_level": impact_level,
        "similar_cases": similar_cases,
        "session_id": session_id,
    }

    sec_similar = retrieve_similar_cases(
        alert_type,
        payload,
        exclude_source_alert_id=alert.get("source_alert_id"),
    )
    yield {
        "event": "memory_retrieved",
        "data": {"agent": "secondary", "similar_cases": sec_similar},
    }

    sec_enrichment = _run_skills(alert_type, payload)
    yield {
        "event": "enrichment_complete",
        "data": {"agent": "secondary", "enrichment": sec_enrichment},
    }

    sec_session = secondary_client.create_session(agent_id="secondary")
    sec_session_id = sec_session.get("id", sec_session.get("session_id", ""))
    if not sec_session_id:
        raise GroqClientError(f"No session ID in secondary response: {sec_session}")

    sec_prompt = secondary_client._build_reinvestigation_prompt(
        alert, alert_type, payload, sec_enrichment, primary_result, sec_similar
    )
    secondary_client.send_message(sec_session_id, sec_prompt)
    logger.info(
        "[handoff] Secondary session %s created and prompt sent for %s — "
        "emitting secondary agent_started.",
        sec_session_id,
        alert.get("source_alert_id"),
    )
    yield {
        "event": "agent_started",
        "data": {
            "agent": "secondary",
            "session_id": sec_session_id,
            "provider": secondary_provider,
        },
    }

    secondary_parts: list[str] = []
    for stream_event in secondary_client.stream_session_events(sec_session_id):
        if stream_event["type"] == "delta":
            secondary_parts.append(stream_event["text"])
            yield {
                "event": "agent_delta",
                "data": {"agent": "secondary", "text": stream_event["text"]},
            }

    secondary_text = "".join(secondary_parts).strip()
    secondary_parsed = parse_agent_response(secondary_text)
    secondary_verdict = secondary_parsed.get("secondary_verdict")
    yield {
        "event": "agent_complete",
        "data": {
            "agent": "secondary",
            "provider": secondary_provider,
            "secondary_verdict": secondary_verdict,
            "verdict": secondary_parsed.get("verdict"),
            "confidence": secondary_parsed.get("confidence"),
            "impact_level": secondary_parsed.get("impact_level"),
            "reasoning": secondary_parsed.get("reasoning", ""),
        },
    }

    if secondary_verdict:
        supabase.table("cases").update(
            {"secondary_verdict": secondary_verdict}
        ).eq("id", case["id"]).execute()

    action_outcome = decide_and_execute_action(
        alert=alert,
        case=case,
        primary_parsed=primary_parsed,
        secondary_parsed=secondary_parsed,
        enrichment=sec_enrichment,
        primary_provider=primary_provider,
        secondary_provider=secondary_provider,
    )

    decision = action_outcome["decision"]
    yield {
        "event": "action_decided",
        "data": {
            "action_id": decision["action_id"],
            "action_class": decision["action_class"],
            "action_status": decision["action_status"],
            "target": decision.get("target"),
            "rationale": decision.get("rationale"),
            "executed": decision["execute"],
            "record": action_outcome["record"],
        },
    }

    yield {
        "event": "investigation_complete",
        "data": {
            "alert_id": alert_id,
            "source_alert_id": alert.get("source_alert_id"),
            "case_id": case["id"],
            "primary_verdict": primary_parsed.get("verdict"),
            "primary_confidence": primary_parsed.get("confidence"),
            "primary_reasoning": primary_parsed.get("reasoning", ""),
            "secondary_verdict": secondary_verdict,
            "secondary_confidence": secondary_parsed.get("confidence"),
            "secondary_reasoning": secondary_parsed.get("reasoning", ""),
            "impact_level": impact_level or secondary_parsed.get("impact_level"),
            "action_id": decision["action_id"],
            "action_status": decision["action_status"],
            "case_closed": action_outcome["case_closed"],
            "alert_status": action_outcome["alert_status"],
            "memory_record_id": action_outcome.get("memory_record_id"),
            "primary_provider": primary_provider,
            "secondary_provider": secondary_provider,
        },
    }

    logger.info(
        "Streamed investigation for %s complete: case %s, %s(%s)/%s(%s), action %s (%s)",
        alert.get("source_alert_id"),
        case["id"],
        primary_parsed.get("verdict"),
        primary_provider,
        secondary_verdict,
        secondary_provider,
        decision["action_id"],
        decision["action_status"],
    )
