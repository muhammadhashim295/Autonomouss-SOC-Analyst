"""Seed the 100 pre-generated high-fidelity scenarios directly into Supabase database.

Every alert is stored with its full payload, pre-computed dual-agent reasoning,
and firewall flags (for poisoned variants), so that the entire system operates
directly on real Supabase database records.
"""

from __future__ import annotations

import argparse
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


def select_scenarios(scenarios: list[dict], limit: int) -> list[dict]:
    """Return `limit` scenarios chosen evenly across categories for variety."""
    if limit <= 0 or limit >= len(scenarios):
        return scenarios
    step = len(scenarios) / limit
    return [scenarios[int(i * step)] for i in range(limit)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed pre-generated SOC demo alerts into Supabase.")
    parser.add_argument("--limit", type=int, default=50, help="Number of alerts to seed, sampled evenly across categories (0 = all).")
    parser.add_argument("--clear", action="store_true", help="Delete existing LIVE-* demo alerts and their flags/cases before seeding.")
    args = parser.parse_args()

    if not DATA_FILE.exists():
        logger.error("Scenarios file %s not found. Run generate_100_scenarios.py first.", DATA_FILE)
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    scenarios = select_scenarios(scenarios, args.limit)
    logger.info("Selected %d scenarios (from %s) to seed.", len(scenarios), DATA_FILE)
    sb = get_supabase()

    # Resolve tenant organizations so seeded alerts are visible whether the demo
    # runs as an admin (sees all) or inside a specific enclave route/client login.
    org_ids: list[str] = []
    try:
        org_rows = sb.table("organizations").select("id").execute().data or []
        org_ids = [o["id"] for o in org_rows if o.get("id")]
    except Exception:
        org_ids = []
    if org_ids:
        logger.info("Cycling alerts across %d organization tenants.", len(org_ids))
    else:
        logger.info("No organizations found; seeding alerts unscoped (admin/ALL view only).")

    if args.clear:
        try:
            existing = sb.table("alerts").select("id").like("source_alert_id", "LIVE-%").execute().data or []
            ids = [r["id"] for r in existing]
            if ids:
                sb.table("firewall_flags").delete().in_("alert_id", ids).execute()
                sb.table("cases").delete().in_("alert_id", ids).execute()
                sb.table("alerts").delete().in_("id", ids).execute()
                logger.info("Cleared %d existing LIVE-* demo alerts before re-seeding.", len(ids))
        except Exception as exc:
            logger.warning("Clear step skipped: %s", exc)

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
            # Stagger received_at so the oldest-first drip order is deterministic.
            offset_sec = (len(scenarios) - global_idx) * 3
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

            row = {
                "source_alert_id": source_id,
                "alert_type": sc["alert_type"],
                "raw_payload": payload,
                "status": "pending",
                "received_at": received_at,
            }
            if org_ids:
                row["org_id"] = org_ids[global_idx % len(org_ids)]
            alert_rows.append(row)
            meta_list.append((source_id, sc["alert_type"], payload, sc.get("is_poisoned", False), row.get("org_id")))

        # Insert alerts chunk into Supabase
        try:
            res = sb.table("alerts").insert(alert_rows).execute()
        except Exception:
            # Fallback if the org_id column is not present yet
            for r in alert_rows:
                r.pop("org_id", None)
            res = sb.table("alerts").insert(alert_rows).execute()
            meta_list = [m[:4] + (None,) for m in meta_list]
        if not res.data:
            logger.error("Failed to insert chunk starting at %d", chunk_idx)
            continue

        inserted_chunk = res.data
        inserted_alerts += len(inserted_chunk)

        # Check and insert firewall flags for poisoned alerts
        flag_rows = []
        for alert_record, (source_id, alert_type, payload, is_poisoned, org_id) in zip(inserted_chunk, meta_list):
            if is_poisoned:
                flags = check_alert(source_id, alert_type, payload)
                if flags:
                    raw_json = json.dumps(payload, ensure_ascii=False)
                    for reason in flags:
                        fr = {
                            "alert_id": alert_record["id"],
                            "flag_reason": reason,
                            "raw_snippet": sanitize_snippet(raw_json),
                        }
                        if org_id:
                            fr["org_id"] = org_id
                        flag_rows.append(fr)

        if flag_rows:
            try:
                sb.table("firewall_flags").insert(flag_rows).execute()
            except Exception:
                for fr in flag_rows:
                    fr.pop("org_id", None)
                sb.table("firewall_flags").insert(flag_rows).execute()
            inserted_flags += len(flag_rows)

        logger.info("Inserted %d/%d alerts into Supabase (firewall flags: %d)", inserted_alerts, len(scenarios), inserted_flags)

    logger.info("Successfully seeded %d alerts and %d firewall flags into Supabase!", inserted_alerts, inserted_flags)


if __name__ == "__main__":
    main()
