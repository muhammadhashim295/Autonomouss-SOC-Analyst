"""Seed the 100 pre-generated high-fidelity scenarios directly into Supabase database.

Every alert is stored with its full payload, pre-computed dual-agent reasoning,
and firewall flags (for poisoned variants), so that the entire system operates
directly on real Supabase database records.
"""

from __future__ import annotations

import json
import logging
import random
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.firewall import check_alert, sanitize_snippet
from app.db.supabase_client import get_supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_db")

DATA_FILE = _BACKEND_DIR / "app" / "data" / "pregenerated_100_alerts.json"


def rand_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def main() -> None:
    if not DATA_FILE.exists():
        logger.error("Scenarios file %s not found.", DATA_FILE)
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    logger.info("Loaded %d scenarios from %s", len(scenarios), DATA_FILE)
    sb = get_supabase()

    now = datetime.now(timezone.utc)
    inserted_alerts = 0
    inserted_flags = 0

    # Batch insert in chunks of 20
    batch_size = 20
    for chunk_idx in range(0, len(scenarios), batch_size):
        chunk = scenarios[chunk_idx : chunk_idx + batch_size]
        alert_rows = []
        meta_list = []

        for i, sc in enumerate(chunk):
            global_idx = chunk_idx + i
            # Stagger received_at over the last 10 minutes so newest appear first
            offset_sec = (len(scenarios) - global_idx) * 6
            received_at = (now - timedelta(seconds=offset_sec)).isoformat()
            ts = int((now - timedelta(seconds=offset_sec)).timestamp())
            source_id = f"LIVE-{ts}-{rand_id()}"

            payload = json.loads(json.dumps(sc["raw_payload"]))
            payload["_scenario_id"] = sc["scenario_id"]
            payload["_primary"] = sc["primary"]
            payload["_secondary"] = sc["secondary"]
            payload["_enrichment"] = sc["enrichment"]
            payload["_impact_level"] = sc["impact_level"]
            payload["_is_poisoned"] = sc.get("is_poisoned", False)

            # Update timestamps inside log_entries
            logs = payload.get("log_entries", [])
            for log_i, log_entry in enumerate(logs):
                log_offset = (len(logs) - log_i) * 3
                log_time = now - timedelta(seconds=offset_sec + log_offset)
                log_entry["timestamp"] = log_time.strftime("%Y-%m-%dT%H:%M:%SZ")

            alert_rows.append({
                "source_alert_id": source_id,
                "alert_type": sc["alert_type"],
                "raw_payload": payload,
                "status": "pending",
                "received_at": received_at,
            })
            meta_list.append((source_id, sc["alert_type"], payload, sc.get("is_poisoned", False)))

        # Insert alerts chunk into Supabase
        res = sb.table("alerts").insert(alert_rows).execute()
        if not res.data:
            logger.error("Failed to insert chunk starting at %d", chunk_idx)
            continue

        inserted_chunk = res.data
        inserted_alerts += len(inserted_chunk)

        # Check and insert firewall flags for poisoned alerts
        flag_rows = []
        for alert_record, (source_id, alert_type, payload, is_poisoned) in zip(inserted_chunk, meta_list):
            if is_poisoned:
                flags = check_alert(source_id, alert_type, payload)
                if flags:
                    raw_json = json.dumps(payload, ensure_ascii=False)
                    for reason in flags:
                        flag_rows.append({
                            "alert_id": alert_record["id"],
                            "flag_reason": reason,
                            "raw_snippet": sanitize_snippet(raw_json),
                        })

        if flag_rows:
            sb.table("firewall_flags").insert(flag_rows).execute()
            inserted_flags += len(flag_rows)

        logger.info("Inserted %d/%d alerts into Supabase (firewall flags: %d)", inserted_alerts, len(scenarios), inserted_flags)

    logger.info("Successfully seeded %d alerts and %d firewall flags into Supabase!", inserted_alerts, inserted_flags)


if __name__ == "__main__":
    main()
