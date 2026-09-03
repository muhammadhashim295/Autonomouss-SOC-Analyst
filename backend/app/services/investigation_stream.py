"""Phase 14 — Live event stream for the dual-agent investigation pipeline.

Runs the same pipeline as ``POST /alerts/{id}/reinvestigate`` (Phases
7-13) but as a generator that yields each stage the moment it happens,
so the backend can relay agent reasoning to the frontend via SSE while
the agents are still thinking.

Event vocabulary (``{"event": name, "data": {...}}``):

- ``investigation_started``  — alert metadata
- ``memory_retrieved``       — similar past cases (per agent)
- ``enrichment_complete``    — the 4-skill results (per agent, fresh)
- ``agent_started``          — agent session created (primary|secondary)
- ``agent_status``           — live session signals (agent.thinking,
                              model spans) relayed the moment they land —
                              the API streams at MESSAGE granularity (one
                              agent.message per turn), so these are the
                              live "agent is working" signals
- ``agent_delta``            — agent reasoning text (the full message,
                              delivered the instant the agent finishes)
- ``agent_complete``         — parsed verdict / confidence / reasoning
- ``case_persisted``         — case row written after the primary run
- ``action_decided``         — Phase 10 action pipeline outcome
- ``investigation_complete`` — final summary (case, verdicts, action)
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from app.db.supabase_client import get_supabase
from app.services.actions import decide_and_execute_action
from app.services.agent_provider import get_agent_client
from app.services.groq_client import GroqClientError
from app.services.investigation import (
    classify_impact,
    parse_agent_response,
    persist_case,
    retrieve_similar_cases,
)
from app.services.qoder_client import QoderClientError
from app.services.skills import (
    correlate_logs,
    detect_deviation,
    enrich_iocs,
    map_attack_techniques,
)


logger = logging.getLogger(__name__)


def _run_skills(alert_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run the 4 investigation skills fresh (each agent derives its own)."""
    return {
        "otx_enrichment": enrich_iocs(payload),
        "attack_mapping": map_attack_techniques(alert_type, payload),
        "log_correlation": correlate_logs(alert_type, payload),
        "behavioral_deviation": detect_deviation(alert_type, payload),
    }


def run_dual_agent_stream(alert: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Full dual-agent investigation as a live event stream (Phase 14).

    Mirrors the reinvestigate endpoint: the primary investigates and its
    case is persisted, the secondary independently re-derives with fresh
    skills, then the enforced action pipeline decides/executes.  Every
    stage is yielded as ``{"event": ..., "data": ...}`` the moment it
    happens — ``agent_delta`` events carry the agents' reasoning live.

    Exceptions propagate to the caller (the SSE layer converts them into
    an ``investigation_error`` event and reverts the alert).
    """
    agent = get_agent_client()

    alert_id = alert["id"]
    alert_type = alert.get("alert_type", "unknown")
    payload = alert.get("raw_payload", {})

    yield {
        "event": "investigation_started",
        "data": {
            "alert_id": alert_id,
            "source_alert_id": alert.get("source_alert_id"),
            "alert_type": alert_type,
            "agent_provider": agent.provider_name,
        },
    }

    # ── Primary Agent ──────────────────────────────────────────────────
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

    session = agent.create_session()
    session_id = session.get("id", session.get("session_id", ""))
    if not session_id:
        raise (QoderClientError if agent.provider_name == "qoder" else GroqClientError)(
            f"No session ID in response: {session}"
        )

    prompt = agent._build_investigation_prompt(
        alert, alert_type, payload, enrichment, similar_cases
    )
    agent.send_message(session_id, prompt)
    yield {
        "event": "agent_started",
        "data": {"agent": "primary", "session_id": session_id, "provider": agent.provider_name},
    }

    primary_parts: list[str] = []
    for stream_event in agent.stream_session_events(session_id):
        if stream_event["type"] == "delta":
            primary_parts.append(stream_event["text"])
            yield {
                "event": "agent_delta",
                "data": {"agent": "primary", "text": stream_event["text"]},
            }
        else:
            # Live session signals (agent.thinking, model spans) relayed
            # the moment they land — the frontend can show the agent
            # working while it thinks.
            yield {
                "event": "agent_status",
                "data": {
                    "agent": "primary",
                    "status": stream_event.get("event"),
                    "detail": stream_event.get("data"),
                },
            }

    primary_text = "".join(primary_parts).strip()
    primary_parsed = parse_agent_response(primary_text)
    yield {
        "event": "agent_complete",
        "data": {
            "agent": "primary",
            "verdict": primary_parsed.get("verdict"),
            "confidence": primary_parsed.get("confidence"),
            "reasoning": primary_parsed.get("reasoning", ""),
            "attack_technique": primary_parsed.get("attack_technique"),
        },
    }

    case = persist_case(
        alert_id=alert_id,
        parsed=primary_parsed,
        enrichment=enrichment,
        impact_level=impact_level,
    )
    yield {"event": "case_persisted", "data": {"case_id": case["id"]}}

    # ── Secondary Agent (independent re-investigation) ─────────────────
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

    # Fresh skills so the secondary re-derives independently (not the
    # primary's cached copy — same contract as reinvestigate_alert).
    sec_enrichment = _run_skills(alert_type, payload)
    yield {
        "event": "enrichment_complete",
        "data": {"agent": "secondary", "enrichment": sec_enrichment},
    }

    sec_session = agent.create_session(agent_id="secondary")
    sec_session_id = sec_session.get("id", sec_session.get("session_id", ""))
    if not sec_session_id:
        raise (QoderClientError if agent.provider_name == "qoder" else GroqClientError)(
            f"No session ID in response: {sec_session}"
        )

    sec_prompt = agent._build_reinvestigation_prompt(
        alert, alert_type, payload, sec_enrichment, primary_result, sec_similar
    )
    agent.send_message(sec_session_id, sec_prompt)
    yield {
        "event": "agent_started",
        "data": {"agent": "secondary", "session_id": sec_session_id, "provider": agent.provider_name},
    }

    secondary_parts: list[str] = []
    for stream_event in agent.stream_session_events(sec_session_id):
        if stream_event["type"] == "delta":
            secondary_parts.append(stream_event["text"])
            yield {
                "event": "agent_delta",
                "data": {"agent": "secondary", "text": stream_event["text"]},
            }
        else:
            yield {
                "event": "agent_status",
                "data": {
                    "agent": "secondary",
                    "status": stream_event.get("event"),
                    "detail": stream_event.get("data"),
                },
            }


    secondary_text = "".join(secondary_parts).strip()
    secondary_parsed = parse_agent_response(secondary_text)
    secondary_verdict = secondary_parsed.get("secondary_verdict")
    yield {
        "event": "agent_complete",
        "data": {
            "agent": "secondary",
            "secondary_verdict": secondary_verdict,
            "verdict": secondary_parsed.get("verdict"),
            "confidence": secondary_parsed.get("confidence"),
            "impact_level": secondary_parsed.get("impact_level"),
            "reasoning": secondary_parsed.get("reasoning", ""),
        },
    }

    # ── Case update + action pipeline (enforced logic) ─────────────────
    if secondary_verdict:
        get_supabase().table("cases").update(
            {"secondary_verdict": secondary_verdict}
        ).eq("id", case["id"]).execute()

    action_outcome = decide_and_execute_action(
        alert=alert,
        case=case,
        primary_parsed=primary_parsed,
        secondary_parsed=secondary_parsed,
        enrichment=sec_enrichment,
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
            "secondary_verdict": secondary_verdict,
            "secondary_confidence": secondary_parsed.get("confidence"),
            "action_id": decision["action_id"],
            "action_status": decision["action_status"],
            "case_closed": action_outcome["case_closed"],
            "alert_status": action_outcome["alert_status"],
            "memory_record_id": action_outcome.get("memory_record_id"),
        },
    }

    logger.info(
        "Streamed investigation for %s complete: case %s, %s/%s, "
        "action %s (%s)",
        alert.get("source_alert_id"),
        case["id"],
        primary_parsed.get("verdict"),
        secondary_verdict,
        decision["action_id"],
        decision["action_status"],
    )
