"""Phase 21 — In-memory store for pre-generated alert scenarios.

Loads backend/app/data/pregenerated_100_alerts.json and provides high-speed,
zero-rate-limit access to pre-computed telemetry, dual-agent reasoning chains,
and forensic skill outputs for the live Command Center and SSE streaming.
"""

from __future__ import annotations

import json
import logging
import random
import string
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "pregenerated_100_alerts.json"

_scenarios: list[dict[str, Any]] = []
_scenario_index: int = 0
_poison_scenarios: list[dict[str, Any]] = []
_clean_scenarios: list[dict[str, Any]] = []


def _rand_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def load_scenarios() -> int:
    """Load scenarios from Supabase database or fallback JSON file into memory."""
    global _scenarios, _scenario_index, _poison_scenarios, _clean_scenarios

    # 1. First attempt to load directly from Supabase database
    try:
        from app.db.supabase_client import get_supabase
        sb = get_supabase()
        res = sb.table("alerts").select("raw_payload, alert_type").order("received_at", desc=True).limit(200).execute()
        db_scenarios = []
        for row in (res.data or []):
            p = row.get("raw_payload")
            if isinstance(p, dict) and "_primary" in p and "_secondary" in p:
                db_scenarios.append({
                    "scenario_id": p.get("_scenario_id", ""),
                    "alert_type": row.get("alert_type"),
                    "is_poisoned": p.get("_is_poisoned", False),
                    "raw_payload": p,
                    "primary": p.get("_primary"),
                    "secondary": p.get("_secondary"),
                    "enrichment": p.get("_enrichment"),
                    "impact_level": p.get("_impact_level", "standard"),
                })
        if len(db_scenarios) >= 50:
            _scenarios = db_scenarios
            _scenario_index = 0
            _poison_scenarios = [s for s in _scenarios if s.get("is_poisoned")]
            _clean_scenarios = [s for s in _scenarios if not s.get("is_poisoned")]
            logger.info(
                "Loaded %d scenarios directly from Supabase database (%d clean, %d poison).",
                len(_scenarios),
                len(_clean_scenarios),
                len(_poison_scenarios),
            )
            return len(_scenarios)
    except Exception as exc:
        logger.warning("Could not query scenarios from Supabase (%s); falling back to local file.", exc)

    # 2. Fallback to local JSON file
    if not _DATA_FILE.exists():
        logger.warning("Pregenerated alerts file %s not found.", _DATA_FILE)
        return 0

    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            _scenarios = data
            _scenario_index = 0
            _poison_scenarios = [s for s in _scenarios if s.get("is_poisoned")]
            _clean_scenarios = [s for s in _scenarios if not s.get("is_poisoned")]
            logger.info(
                "Loaded %d pre-generated scenarios from local file (%d clean, %d poison).",
                len(_scenarios),
                len(_clean_scenarios),
                len(_poison_scenarios),
            )
            return len(_scenarios)
    except Exception as exc:
        logger.error("Failed to load pre-generated scenarios from %s: %s", _DATA_FILE, exc)

    return 0


def is_available() -> bool:
    """Check if scenarios are loaded."""
    if not _scenarios:
        load_scenarios()
    return len(_scenarios) > 0


def get_scenario_count() -> int:
    """Return total number of scenarios loaded."""
    if not _scenarios:
        load_scenarios()
    return len(_scenarios)


def get_next_live_alert(inject_poison: bool = False) -> dict[str, Any]:
    """Return a fresh alert stamped with current UTC time and a unique source ID.

    Cycles through pre-generated scenarios so that every attack type is represented,
    with dynamically updated timestamps so the logs appear live.
    """
    global _scenario_index

    if not _scenarios:
        load_scenarios()

    if not _scenarios:
        raise RuntimeError("No pre-generated scenarios available in memory.")

    # Select scenario
    if inject_poison and _poison_scenarios:
        base = random.choice(_poison_scenarios)
    elif not inject_poison and _clean_scenarios:
        base = _clean_scenarios[_scenario_index % len(_clean_scenarios)]
        _scenario_index += 1
    else:
        base = _scenarios[_scenario_index % len(_scenarios)]
        _scenario_index += 1

    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    source_id = f"LIVE-{now_ts}-{_rand_id()}"
    alert_type = base["alert_type"]

    # Clone payload and adjust timestamps to be relative to now
    payload = json.loads(json.dumps(base["raw_payload"]))
    logs = payload.get("log_entries", [])
    for i, entry in enumerate(logs):
        offset = len(logs) - i
        entry_time = now - timedelta(seconds=offset * 4)
        entry["timestamp"] = entry_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Store complete scenario reference inside payload for instant retrieval by stream and Supabase persistence
    payload["_scenario_id"] = base.get("scenario_id")
    payload["_primary"] = base.get("primary")
    payload["_secondary"] = base.get("secondary")
    payload["_enrichment"] = base.get("enrichment")
    payload["_impact_level"] = base.get("impact_level")
    payload["_is_poisoned"] = base.get("is_poisoned", False)

    return {
        "source_alert_id": source_id,
        "alert_type": alert_type,
        "raw_payload": payload,
        "scenario_ref": base,
    }


def find_scenario_for_alert(alert: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Locate the matching pre-generated scenario for an alert directly from DB row or memory store."""
    payload = alert.get("raw_payload", {})
    if isinstance(payload, dict) and "_primary" in payload and "_secondary" in payload:
        return {
            "scenario_id": payload.get("_scenario_id", f"db-{alert.get('id', '')[:8]}"),
            "alert_type": alert.get("alert_type", "unknown"),
            "is_poisoned": payload.get("_is_poisoned", False),
            "raw_payload": payload,
            "primary": payload.get("_primary"),
            "secondary": payload.get("_secondary"),
            "enrichment": payload.get("_enrichment"),
            "impact_level": payload.get("_impact_level", "standard"),
        }

    if not _scenarios:
        load_scenarios()

    ref_id = payload.get("_scenario_id")
    if ref_id:
        for s in _scenarios:
            if s.get("scenario_id") == ref_id:
                return s

    # Match by alert type
    alert_type = alert.get("alert_type")
    candidates = [s for s in _scenarios if s.get("alert_type") == alert_type]
    if candidates:
        return random.choice(candidates)

    if _scenarios:
        return _scenarios[0]

    return None
