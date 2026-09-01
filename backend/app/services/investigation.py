"""Phase 7 — Full investigation flow.

Wires together:
- Response parser (extract structured fields from agent text)
- Impact classification (standard vs high_impact — real logic, not LLM discretion)
- Memory store stub (TODO: Phase 11)
- Case persistence (write to Supabase cases table)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ── 1. Response parser ────────────────────────────────────────────────────────


def parse_agent_response(text: str) -> dict[str, Any]:
    """Parse the agent's markdown investigation report into structured fields.

    Extracts:
    - verdict: false_positive | true_positive
    - confidence: float 0-1
    - reasoning: the full evidence-cited reasoning text
    - self_audit: what could change the verdict
    - attack_technique: ATT&CK ID (e.g. T1110.001)

    The parser takes the **last** match for verdict/confidence so that
    if the agent echoes the prompt (which contains the same keywords),
    the actual response wins.

    Returns a dict with all fields.  Missing fields default to safe values.
    """
    result: dict[str, Any] = {
        "verdict": "true_positive",
        "confidence": 0.5,
        "reasoning": "",
        "self_audit": "",
        "attack_technique": None,
        "secondary_verdict": None,
    }

    if not text:
        return result

    # ── Verdict ───────────────────────────────────────────────────────────
    # Use findall + take LAST match to handle echoed prompts.
    # Match both **Verdict:** (colon inside bold) and **Verdict**: (outside).
    bold_verdicts = re.findall(
        r"\*\*Verdict:?\*\*\s*[:\-]?\s*(false_positive|true_positive)",
        text,
        re.IGNORECASE,
    )
    if bold_verdicts:
        result["verdict"] = bold_verdicts[-1].lower()
    else:
        # Fallback: line-anchored plain verdict
        plain_verdicts = re.findall(
            r"(?:^|\n)\s*Verdict\s*[:\-]\s*(false_positive|true_positive)",
            text,
            re.IGNORECASE,
        )
        if plain_verdicts:
            result["verdict"] = plain_verdicts[-1].lower()

    # ── Confidence ────────────────────────────────────────────────────────
    # Match **Confidence:** followed by a NUMBER.
    # Handle both **Confidence:** (colon inside) and **Confidence**: (outside).
    bold_confs = re.findall(
        r"\*\*Confidence:?\*\*\s*[:\-]?\s*([\d.]+)",
        text,
        re.IGNORECASE,
    )
    if bold_confs:
        last = bold_confs[-1]
        try:
            val = float(last)
            if val > 1.0:
                val = val / 100.0
            result["confidence"] = max(0.0, min(1.0, val))
        except ValueError:
            pass
    else:
        # Fallback: line-anchored plain confidence
        plain_confs = re.findall(
            r"(?:^|\n)\s*Confidence\s*[:\-]\s*([\d.]+)",
            text,
            re.IGNORECASE,
        )
        if plain_confs:
            try:
                val = float(plain_confs[-1])
                if val > 1.0:
                    val = val / 100.0
                result["confidence"] = max(0.0, min(1.0, val))
            except ValueError:
                pass

    # ── ATT&CK technique ──────────────────────────────────────────────────
    attack_matches = re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text)
    if attack_matches:
        # Take the last match (likely from the agent's actual analysis,
        # not from the prompt's skill output section)
        result["attack_technique"] = attack_matches[-1]

    # ── Secondary verdict (agree/disagree — Phase 8+) ───────────────────
    # Extracted BEFORE regular verdict so a "Secondary Verdict" line does
    # not shadow the primary-verdict regex (which only matches FP/TP words).
    secondary = re.findall(
        r"\*\*Secondary\s*Verdict:?[\*]*\s*[:\-]?\s*"
        r"(false_positive|true_positive|agree|disagree)",
        text,
        re.IGNORECASE,
    )
    result["secondary_verdict"] = secondary[-1].lower() if secondary else None

    # ── Impact level (Phase 8+ secondary reports) ───────────────────────
    impact = re.findall(
        r"\*\*Impact\s*Level:?[\*]*\s*[:\-]?\s*(standard|high[_\-\s]?impact)",
        text,
        re.IGNORECASE,
    )
    if impact:
        result["impact_level"] = impact[-1].lower().replace(" ", "_").replace("-", "_")
    else:
        result["impact_level"] = None

    # ── Reasoning (between Reasoning/Evidence and Self-Audit sections) ────
    # Patterns handle both **Key:** (colon inside) and **Key**: (outside).
    reasoning = _extract_section(text, [
        r"\*\*Reasoning:?\*\*",
        r"\*\*Evidence.*Reasoning:?\*\*",
        r"##\s*Reasoning",
        r"##\s*Evidence",
    ], [
        r"\*\*Self[\-\s]*Audit:?\*\*",
        r"\*\*Next\s*Action:?\*\*",
        r"##\s*Self[\-\s]*Audit",
        r"##\s*Next",
    ])
    result["reasoning"] = reasoning.strip() if reasoning else text[:2000]

    # ── Self-audit ────────────────────────────────────────────────────────
    self_audit = _extract_section(text, [
        r"\*\*Self[\-\s]*Audit:?\*\*",
        r"##\s*Self[\-\s]*Audit",
    ], [
        r"\*\*Next\s*Action:?\*\*",
        r"##\s*Next",
    ])
    result["self_audit"] = self_audit.strip() if self_audit else ""

    return result


def _extract_section(
    text: str,
    start_patterns: list[str],
    end_patterns: list[str],
) -> str:
    """Extract text between the first matching start pattern and end pattern."""
    start_pos = None
    for pattern in start_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            start_pos = m.end()
            break

    if start_pos is None:
        return ""

    end_pos = len(text)
    for pattern in end_patterns:
        m = re.search(pattern, text[start_pos:], re.IGNORECASE)
        if m:
            end_pos = start_pos + m.start()
            break

    return text[start_pos:end_pos]


# ── 2. Impact classification ──────────────────────────────────────────────────

# Alert types that always classify as high-impact
_HIGH_IMPACT_ALERT_TYPES = {"data_exfiltration", "lateral_movement"}

# Asset tags that trigger high-impact classification
_CRITICAL_ASSET_TAGS = {"critical-asset", "domain-controller", "prod-db", "exec-account"}

# Hostname patterns for critical assets
_CRITICAL_HOSTNAME_PATTERNS = [
    re.compile(r"SRV-DC", re.I),        # Domain controllers
    re.compile(r"SRV-DB", re.I),         # Database servers
    re.compile(r"SRV-EXCHANGE", re.I),   # Exchange servers
    re.compile(r"SRV-PROD", re.I),       # Production servers
]


def classify_impact(alert_type: str, payload: dict[str, Any]) -> str:
    """Determine whether the alert's required action is standard or high_impact.

    This is real enforced logic (per design.md), not LLM discretion.

    Returns ``"standard"`` or ``"high_impact"``.
    """
    # 1. Alert type check
    if alert_type in _HIGH_IMPACT_ALERT_TYPES:
        return "high_impact"

    # 2. Critical asset tags
    asset_tags = set(payload.get("asset_tags", []))
    if asset_tags & _CRITICAL_ASSET_TAGS:
        return "high_impact"

    # 3. Critical hostname patterns
    hostname = payload.get("hostname", "")
    for pattern in _CRITICAL_HOSTNAME_PATTERNS:
        if pattern.search(hostname):
            return "high_impact"

    # 4. Data volume check (large transfers = high impact)
    bytes_sent = payload.get("bytes_sent", 0)
    if isinstance(bytes_sent, (int, float)) and bytes_sent > 100_000_000:  # >100 MB
        return "high_impact"

    return "standard"


# ── 3. Memory store (Phase 11) ─────────────────────────────────────────────────


def retrieve_similar_cases(
    alert_type: str,
    payload: dict[str, Any],
    limit: int = 3,
    exclude_source_alert_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve similar past cases from the memory store.

    Phase 11: implemented in :mod:`app.services.memory_store` — this is a
    thin façade so existing imports keep working.  Records are scored by
    shared IOCs, source IP, asset tags, and recency, with analyst
    corrections boosted.  Returns [] on failure (investigation proceeds
    without memory).
    """
    from app.services.memory_store import retrieve_similar_cases as _retrieve

    return _retrieve(
        alert_type,
        payload,
        limit=limit,
        exclude_source_alert_id=exclude_source_alert_id,
    )


# ── 4. Case persistence ──────────────────────────────────────────────────────


def persist_case(
    alert_id: str,
    parsed: dict[str, Any],
    enrichment: dict[str, Any],
    impact_level: str,
) -> dict[str, Any]:
    """Write the investigation result to the ``cases`` table in Supabase.

    Parameters
    ----------
    alert_id : str
        UUID of the alert in the ``alerts`` table.
    parsed : dict
        Output of :func:`parse_agent_response` — verdict, confidence,
        reasoning, self_audit, attack_technique.
    enrichment : dict
        The 4-skill enrichment results.
    impact_level : str
        Output of :func:`classify_impact` — ``"standard"`` or ``"high_impact"``.

    Returns the inserted case row.
    """
    supabase = get_supabase()

    case_row = {
        "alert_id": alert_id,
        "mode": "agentic",  # Default mode; Phase 12 adds the toggle
        "primary_verdict": parsed["verdict"],
        "primary_confidence": parsed["confidence"],
        "attack_technique": parsed.get("attack_technique"),
        "impact_level": impact_level,
        "action_taken": None,
        "action_status": "none",
        "closed_at": None,
        "qoder_memory_record_id": None,
    }

    result = supabase.table("cases").insert(case_row).execute()

    if not result.data:
        raise RuntimeError("Failed to insert case into Supabase")

    case = result.data[0]

    # Also store the full reasoning and self-audit as enrichment metadata
    # (the cases table doesn't have columns for these — they live in the
    # Qoder Memory Store record in Phase 11.  For now, we store them
    # in a supplementary dict that the endpoint can return.)
    case["reasoning"] = parsed.get("reasoning", "")
    case["self_audit"] = parsed.get("self_audit", "")
    case["enrichment_summary"] = enrichment

    logger.info(
        "Case %s persisted for alert %s: verdict=%s, confidence=%.2f, impact=%s",
        case["id"],
        alert_id,
        parsed["verdict"],
        parsed["confidence"],
        impact_level,
    )

    return case
