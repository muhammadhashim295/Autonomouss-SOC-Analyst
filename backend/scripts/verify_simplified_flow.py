#!/usr/bin/env python3
"""End-to-end verification of the simplified 2-provider pipeline & fixed flow.

Tests:
1. Mode toggle removal: /settings/mode returns 404 (completely gone).
2. Scenario 1 (Clean FP): GUIDE-FP-001 -> Primary closes as FP, no Secondary run.
3. Scenario 2 (Standard TP): GUIDE-TP-001 -> Primary TP -> Secondary TP -> autonomous execution (no mode).
4. Scenario 3 (High-Impact TP): GUIDE-HI-001 -> Primary TP -> Secondary TP -> high impact human-gated.
5. Scenario 4 (Poisoned Alert): GUIDE-POISON-001 -> Firewall flags -> direct human escalation, 0 agent calls.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Ensure UTF-8 output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from fastapi.testclient import TestClient
from app.main import app
from app.db.supabase_client import get_supabase

client = TestClient(app)
supabase = get_supabase()

PASS = "[PASS]"
FAIL = "[FAIL]"

SAMPLES_PATH = BACKEND_DIR / "app" / "data" / "sample_alerts.json"
with open(SAMPLES_PATH, encoding="utf-8") as f:
    ALERTS_DICT = {a["source_alert_id"]: a for a in json.load(f)}


def clean_db_for_test(source_alert_id: str) -> None:
    """Clean up previous test rows for this alert ID."""
    try:
        res = supabase.table("alerts").select("id").eq("source_alert_id", source_alert_id).execute()
        for row in (res.data or []):
            aid = row["id"]
            cases = supabase.table("cases").select("id").eq("alert_id", aid).execute()
            for c in (cases.data or []):
                supabase.table("analyst_overrides").delete().eq("case_id", c["id"]).execute()
            supabase.table("memory_records").delete().eq("alert_id", aid).execute()
            supabase.table("firewall_flags").delete().eq("alert_id", aid).execute()
            supabase.table("cases").delete().eq("alert_id", aid).execute()
            supabase.table("alerts").delete().eq("id", aid).execute()
    except Exception as exc:
        print(f"    Cleanup warning for {source_alert_id}: {exc}")


def parse_sse_stream(response) -> list[dict[str, Any]]:
    """Parse SSE text/event-stream response into list of event dicts."""
    events = []
    current_event = None
    for line in response.text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:") and current_event:
            data_str = line[len("data:"):].strip()
            try:
                data = json.loads(data_str)
            except Exception:
                data = {"raw": data_str}
            events.append({"event": current_event, "data": data})
            current_event = None
    return events


def test_mode_toggle_removal() -> bool:
    print("\n" + "=" * 70)
    print("TEST 1: Confirm system_settings mode toggle is fully removed")
    print("=" * 70)

    r_get = client.get("/settings/mode")
    r_put = client.put("/settings/mode", json={"mode": "approval"})

    ok_get = (r_get.status_code == 404)
    ok_put = (r_put.status_code == 404)

    print(f"  GET /settings/mode -> {r_get.status_code} (expect 404): {PASS if ok_get else FAIL}")
    print(f"  PUT /settings/mode -> {r_put.status_code} (expect 404): {PASS if ok_put else FAIL}")

    return ok_get and ok_put


def test_scenario_1_clean_fp() -> bool:
    print("\n" + "=" * 70)
    print("TEST 2: Scenario 1 — Clean Alert (GUIDE-FP-001)")
    print("Requirement: Primary closes as FP, no Secondary involvement, documented")
    print("=" * 70)

    clean_db_for_test("GUIDE-FP-001")
    payload = ALERTS_DICT["GUIDE-FP-001"]

    # 1. Ingest alert
    r_ingest = client.post("/alerts/", json=payload)
    if r_ingest.status_code != 201:
        print(f"  {FAIL} Ingestion failed: {r_ingest.status_code} {r_ingest.text}")
        return False
    alert_id = r_ingest.json()["id"]
    print(f"  Alert ingested: id={alert_id}")

    # 2. Run investigation via SSE stream
    r_stream = client.post(f"/alerts/{alert_id}/investigate/stream")
    if r_stream.status_code != 200:
        print(f"  {FAIL} Investigation stream failed: {r_stream.status_code} {r_stream.text}")
        return False

    events = parse_sse_stream(r_stream)
    event_names = [e["event"] for e in events]
    print(f"  SSE Events received: {event_names}")

    # Verify Primary verdict
    primary_event = next((e for e in events if e["event"] == "agent_complete" and e["data"].get("agent") == "primary"), None)
    complete_event = next((e for e in events if e["event"] == "investigation_complete"), None)
    secondary_started = any(e["event"] == "agent_started" and e["data"].get("agent") == "secondary" for e in events)

    primary_verdict = primary_event["data"].get("verdict") if primary_event else None
    print(f"  Primary verdict: {primary_verdict}")
    print(f"  Secondary agent started: {secondary_started} (expect False for FP)")

    # Verify Database state
    alert_db = supabase.table("alerts").select("*").eq("id", alert_id).execute()
    case_db = supabase.table("cases").select("*").eq("alert_id", alert_id).execute()

    alert_status = alert_db.data[0]["status"] if alert_db.data else None
    case_row = case_db.data[0] if case_db.data else {}

    print(f"  Alert DB status: {alert_status} (expect 'closed')")
    print(f"  Case DB action_status: {case_row.get('action_status')} (expect 'none' or 'auto_closed')")
    print(f"  Case DB closed_at: {case_row.get('closed_at')}")
    print(f"  Case DB primary_verdict: {case_row.get('primary_verdict')}")
    print(f"  Case DB secondary_provider: {case_row.get('secondary_provider')} (expect None)")

    ok = (
        primary_verdict == "false_positive"
        and not secondary_started
        and alert_status == "closed"
        and case_row.get("action_status") in ("none", "auto_closed")
        and case_row.get("closed_at") is not None
        and case_row.get("secondary_provider") is None
    )

    print(f"  RESULT: {PASS if ok else FAIL} Primary closed clean alert as FP with zero Secondary involvement")
    return ok


def test_scenario_2_standard_tp() -> bool:
    print("\n" + "=" * 70)
    print("TEST 3: Scenario 2 — Standard Impact TP (GUIDE-TP-001)")
    print("Requirement: Primary TP -> Secondary TP -> autonomous execution (NO mode setting)")
    print("=" * 70)

    clean_db_for_test("GUIDE-TP-001")
    payload = ALERTS_DICT["GUIDE-TP-001"]

    # 1. Ingest alert
    r_ingest = client.post("/alerts/", json=payload)
    if r_ingest.status_code != 201:
        print(f"  {FAIL} Ingestion failed: {r_ingest.status_code} {r_ingest.text}")
        return False
    alert_id = r_ingest.json()["id"]
    print(f"  Alert ingested: id={alert_id}")

    # 2. Run investigation via SSE stream
    r_stream = client.post(f"/alerts/{alert_id}/investigate/stream")
    if r_stream.status_code != 200:
        print(f"  {FAIL} Investigation stream failed: {r_stream.status_code} {r_stream.text}")
        return False

    events = parse_sse_stream(r_stream)
    event_names = [e["event"] for e in events]
    print(f"  SSE Events received: {event_names}")

    primary_event = next((e for e in events if e["event"] == "agent_complete" and e["data"].get("agent") == "primary"), None)
    secondary_event = next((e for e in events if e["event"] == "agent_complete" and e["data"].get("agent") == "secondary"), None)
    action_event = next((e for e in events if e["event"] == "action_decided"), None)

    p_verdict = primary_event["data"].get("verdict") if primary_event else None
    s_verdict = secondary_event["data"].get("verdict") if secondary_event else None
    act_data = action_event["data"] if action_event else {}

    print(f"  Primary verdict: {p_verdict} (expect true_positive)")
    print(f"  Secondary verdict: {s_verdict} (expect true_positive)")
    print(f"  Action decided: {act_data.get('action_id')} | class={act_data.get('action_class')} | status={act_data.get('action_status')}")
    print(f"  Action executed autonomously: {act_data.get('executed')}")

    # Check DB
    case_db = supabase.table("cases").select("*").eq("alert_id", alert_id).execute()
    case_row = case_db.data[0] if case_db.data else {}

    ok = (
        p_verdict == "true_positive"
        and s_verdict == "true_positive"
        and act_data.get("action_class") == "standard"
        and act_data.get("executed") is True
        and case_row.get("action_status") == "executed"
    )

    print(f"  RESULT: {PASS if ok else FAIL} Standard TP executed autonomously without any mode check")
    return ok


def test_scenario_3_high_impact() -> bool:
    print("\n" + "=" * 70)
    print("TEST 4: Scenario 3 — High-Impact Action (GUIDE-HI-001)")
    print("Requirement: Primary TP -> Secondary TP -> high-impact classification -> ALWAYS human-gated")
    print("=" * 70)

    clean_db_for_test("GUIDE-HI-001")
    payload = ALERTS_DICT["GUIDE-HI-001"]

    # 1. Ingest alert
    r_ingest = client.post("/alerts/", json=payload)
    if r_ingest.status_code != 201:
        print(f"  {FAIL} Ingestion failed: {r_ingest.status_code} {r_ingest.text}")
        return False
    alert_id = r_ingest.json()["id"]
    print(f"  Alert ingested: id={alert_id}")

    # 2. Run investigation via SSE stream
    r_stream = client.post(f"/alerts/{alert_id}/investigate/stream")
    if r_stream.status_code != 200:
        print(f"  {FAIL} Investigation stream failed: {r_stream.status_code} {r_stream.text}")
        return False

    events = parse_sse_stream(r_stream)
    action_event = next((e for e in events if e["event"] == "action_decided"), None)
    act_data = action_event["data"] if action_event else {}

    print(f"  Action decided: {act_data.get('action_id')} | class={act_data.get('action_class')} | status={act_data.get('action_status')}")
    print(f"  Action executed: {act_data.get('executed')} (expect False)")
    alert_db = supabase.table("alerts").select("status").eq("id", alert_id).execute()
    alert_status = alert_db.data[0]["status"] if alert_db.data else None
    print(f"  Alert DB status: {alert_status} (expect in_review)")

    # Check DB
    case_db = supabase.table("cases").select("*").eq("alert_id", alert_id).execute()
    case_row = case_db.data[0] if case_db.data else {}

    print(f"  Case DB impact_level: {case_row.get('impact_level')} (expect high_impact)")
    print(f"  Case DB action_status: {case_row.get('action_status')} (expect awaiting_approval)")

    ok = (
        act_data.get("action_class") == "high_impact"
        and act_data.get("action_status") == "awaiting_approval"
        and act_data.get("executed") is False
        and case_row.get("impact_level") == "high_impact"
        and case_row.get("action_status") == "awaiting_approval"
    )

    print(f"  RESULT: {PASS if ok else FAIL} High impact alert was strictly gated on human approval")
    return ok


def test_scenario_4_firewall_poison() -> bool:
    print("\n" + "=" * 70)
    print("TEST 5: Scenario 4 — Poisoned Alert (GUIDE-POISON-001)")
    print("Requirement: Firewall flags -> escalates DIRECTLY to human, 0 agent calls")
    print("=" * 70)

    clean_db_for_test("GUIDE-POISON-001")
    payload = ALERTS_DICT["GUIDE-POISON-001"]

    # 1. Ingest alert
    r_ingest = client.post("/alerts/", json=payload)
    if r_ingest.status_code != 201:
        print(f"  {FAIL} Ingestion failed: {r_ingest.status_code} {r_ingest.text}")
        return False

    alert_id = r_ingest.json()["id"]
    ingest_status = r_ingest.json().get("status")
    print(f"  Alert ingested: id={alert_id} | status={ingest_status} (expect in_review)")

    # Check firewall flags written
    flags_res = supabase.table("firewall_flags").select("*").eq("alert_id", alert_id).execute()
    flags = [r["flag_reason"] for r in (flags_res.data or [])]
    print(f"  Firewall flags caught: {flags}")

    # Check immediate direct escalation case creation
    case_res = supabase.table("cases").select("*").eq("alert_id", alert_id).execute()
    case_row = case_res.data[0] if case_res.data else {}

    print(f"  Direct case created: action_status={case_row.get('action_status')} (expect awaiting_approval)")
    print(f"  Case primary_provider: {case_row.get('primary_provider')} (expect firewall)")
    print(f"  Case impact_level: {case_row.get('impact_level')} (expect high_impact)")

    # 2. Call investigation stream -> must immediately return direct escalation without Groq calls!
    r_stream = client.post(f"/alerts/{alert_id}/investigate/stream")
    events = parse_sse_stream(r_stream)
    event_names = [e["event"] for e in events]
    print(f"  SSE Events on flagged alert: {event_names}")

    # Verify no agent deltas or agent turns took place
    agent_deltas = [e for e in events if e["event"] == "agent_delta"]
    print(f"  Agent delta tokens streamed: {len(agent_deltas)} (expect 0)")

    action_event = next((e for e in events if e["event"] == "action_decided"), None)
    direct_escalated = action_event and action_event["data"].get("action_status") == "awaiting_approval"

    ok = (
        len(flags) > 0
        and ingest_status == "in_review"
        and case_row.get("action_status") == "awaiting_approval"
        and case_row.get("primary_provider") == "firewall"
        and len(agent_deltas) == 0
        and direct_escalated
    )

    print(f"  RESULT: {PASS if ok else FAIL} Poisoned alert escalated DIRECTLY to human with zero agent reasoning calls")
    return ok


def main() -> int:
    print("=" * 70)
    print("AUTONOMOUS SOC ANALYST — SIMPLIFICATION & FIXED FLOW VERIFICATION")
    print("=" * 70)

    results = {
        "Mode Toggle Removal": test_mode_toggle_removal(),
        "Scenario 1 (Clean FP)": test_scenario_1_clean_fp(),
        "Scenario 2 (Standard TP Autonomous)": test_scenario_2_standard_tp(),
        "Scenario 3 (High-Impact Gated)": test_scenario_3_high_impact(),
        "Scenario 4 (Direct Firewall Escalation)": test_scenario_4_firewall_poison(),
    }

    print("\n" + "=" * 70)
    print("FINAL TEST SUMMARY")
    print("=" * 70)
    all_passed = True
    for name, passed in results.items():
        print(f"  {PASS if passed else FAIL} {name}")
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("ALL SCENARIOS PASSED CLEANLY! System is verified.")
        return 0
    else:
        print("SOME TESTS FAILED! Please review details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
