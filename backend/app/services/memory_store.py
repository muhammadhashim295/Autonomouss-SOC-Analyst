"""Phase 11 — Memory store: structured case records + similarity retrieval.

Storage: the ``memory_records`` Supabase table (migration 002).  The Qoder
Cloud Agents API has no native memory endpoint (probed: /memories, /memory,
/knowledge all 404; /vaults is a credentials container only), so the store
lives in Supabase and ``cases.qoder_memory_record_id`` points at the record.

Design (design.md "Memory records"): every closed case writes one structured
record — alert metadata, evidence gathered, ATT&CK technique, cross-checked
verdict + confidence, reasoning, response taken, mode, and (Phase 13)
analyst corrections.  Corrections are retrieved with higher priority.

Retrieval: candidate fetch by alert_type, then similarity scoring in Python
(shared IOCs > shared source IP > shared asset tags > recency), with a
priority boost for correction records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.supabase_client import get_supabase
from app.services.skills.otx_enrichment import extract_iocs

logger = logging.getLogger(__name__)


# ── Similarity scoring weights ───────────────────────────────────────────────

_W_SHARED_IOC = 4        # Same attacker infrastructure — strongest signal
_W_SOURCE_IP = 3         # Same source host/IP
_W_ASSET_TAG = 1         # Same asset context (per shared tag, capped)
_W_CORRECTION = 5        # Analyst corrections outrank plain cases
_W_RECENT = 1            # Within the last 7 days
_MIN_SCORE = 2           # Need at least some signal beyond alert_type
_CANDIDATE_LIMIT = 50    # How many same-type records to fetch for scoring

_RECENT_WINDOW_DAYS = 7


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _record_age_days(record: dict[str, Any]) -> float:
    created = record.get("created_at")
    if not created:
        return 999.0
    try:
        ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except ValueError:
        return 999.0
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400


# ── Write path ───────────────────────────────────────────────────────────────


def write_case_record(
    *,
    alert: dict[str, Any],
    case: dict[str, Any],
    primary_parsed: dict[str, Any],
    enrichment: Optional[dict[str, Any]],
    action_record: Optional[dict[str, Any]],
    secondary_parsed: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Write a structured memory record for a closing case.

    Returns the new record's id (also persisted to
    ``cases.qoder_memory_record_id``), or ``None`` on failure — a memory
    write failure must never break the case-closing flow.
    """
    payload = alert.get("raw_payload", {})
    iocs = extract_iocs(payload)
    ioc_keys = list(dict.fromkeys(iocs["ips"] + iocs["domains"] + iocs["hashes"]))

    evidence = dict(enrichment or {})
    if secondary_parsed:
        # The cross-check outcome is part of the evidence trail
        evidence["secondary_cross_check"] = {
            "secondary_verdict": secondary_parsed.get("secondary_verdict"),
            "confidence": secondary_parsed.get("confidence"),
        }

    record = {
        "record_type": "case",
        "alert_id": alert.get("id"),
        "case_id": case.get("id"),
        "source_alert_id": alert.get("source_alert_id", "unknown"),
        "alert_type": alert.get("alert_type", "unknown"),
        "evidence_gathered": evidence,
        "attack_technique": case.get("attack_technique")
        or primary_parsed.get("attack_technique"),
        "verdict": case.get("primary_verdict", "true_positive"),
        "confidence": case.get("primary_confidence", 0.5),
        "reasoning": (primary_parsed.get("reasoning") or "")[:2000],
        "response_taken": action_record,
        "mode": case.get("mode", "agentic"),
        "analyst_correction": None,  # Phase 13 — analyst decision handling
        "iocs": ioc_keys,
        "source_ip": payload.get("source_ip"),
        "asset_tags": _as_list(payload.get("asset_tags")),
    }

    supabase = get_supabase()
    try:
        result = supabase.table("memory_records").insert(record).execute()
        if not result.data:
            raise RuntimeError("insert returned no rows")
        record_id = result.data[0]["id"]

        # Point the case back at its full memory record
        supabase.table("cases").update(
            {"qoder_memory_record_id": record_id}
        ).eq("id", case["id"]).execute()

        logger.info(
            "Memory record %s written for case %s (%s, %s)",
            record_id, case.get("id"), alert.get("source_alert_id"),
            record["verdict"],
        )
        return record_id
    except Exception as exc:  # noqa: BLE001 — memory must never break the flow
        logger.warning("Memory record write failed for case %s: %s", case.get("id"), exc)
        return None


# ── Read path ────────────────────────────────────────────────────────────────


def _score_record(record: dict[str, Any], payload: dict[str, Any]) -> int:
    """Score how similar a past record is to the incoming alert."""
    score = 0

    # Shared IOCs (attacker infrastructure reuse)
    iocs = extract_iocs(payload)
    current = set(iocs["ips"] + iocs["domains"] + iocs["hashes"])
    past = {str(i) for i in _as_list(record.get("iocs"))}
    if current & past:
        score += _W_SHARED_IOC

    # Same source IP
    if payload.get("source_ip") and record.get("source_ip") == payload.get("source_ip"):
        score += _W_SOURCE_IP

    # Shared asset tags (capped at +2)
    current_tags = set(_as_list(payload.get("asset_tags")))
    past_tags = {str(t) for t in _as_list(record.get("asset_tags"))}
    score += min(_W_ASSET_TAG * len(current_tags & past_tags), 2)

    # Corrections carry priority (design.md)
    if record.get("record_type") == "correction":
        score += _W_CORRECTION

    # Recency
    if _record_age_days(record) <= _RECENT_WINDOW_DAYS:
        score += _W_RECENT

    return score


def _format_for_prompt(record: dict[str, Any], score: int) -> dict[str, Any]:
    """Render a memory record compactly for the agent prompt."""
    response = record.get("response_taken") or {}
    return {
        "source_alert_id": record.get("source_alert_id"),
        "alert_type": record.get("alert_type"),
        "record_type": record.get("record_type"),
        "verdict": record.get("verdict"),
        "confidence": record.get("confidence"),
        "attack_technique": record.get("attack_technique"),
        "reasoning": (record.get("reasoning") or "")[:600],
        "action_taken": response.get("action"),
        "action_result": response.get("result"),
        "source_ip": record.get("source_ip"),
        "iocs": record.get("iocs"),
        "closed": str(record.get("created_at", ""))[:19],
        "similarity_score": score,
    }


def retrieve_similar_cases(
    alert_type: str,
    payload: dict[str, Any],
    limit: int = 3,
    exclude_source_alert_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve similar past cases from the memory store.

    Candidates are fetched by alert_type, scored by shared IOCs / source IP /
    asset tags / recency, with correction records boosted.  Returns up to
    ``limit`` formatted records (empty list on any failure — the
    investigation proceeds without memory).

    ``exclude_source_alert_id`` prevents an alert from retrieving its own
    record on re-runs.
    """
    supabase = get_supabase()

    try:
        result = (
            supabase.table("memory_records")
            .select("*")
            .eq("alert_type", alert_type)
            .order("created_at", desc=True)
            .limit(_CANDIDATE_LIMIT)
            .execute()
        )
        candidates = result.data or []
    except Exception as exc:  # noqa: BLE001 — retrieval failure is non-fatal
        logger.warning("Memory retrieval failed for %s: %s", alert_type, exc)
        return []

    current_sid = exclude_source_alert_id or payload.get("source_alert_id")

    scored: list[tuple[int, dict[str, Any]]] = []
    for record in candidates:
        # Never retrieve the alert's own record (re-runs)
        if record.get("source_alert_id") == current_sid and current_sid:
            continue
        score = _score_record(record, payload)
        if score >= _MIN_SCORE:
            scored.append((score, record))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    if scored:
        logger.info(
            "Memory retrieval for %s: %d candidate(s), top score %d",
            alert_type, len(scored), scored[0][0],
        )
    return [_format_for_prompt(rec, score) for score, rec in scored[:limit]]
