"""Phase 11 verification — memory store + case retrieval + learning.

Verify condition (phases.md): "two similar alerts in sequence — second
references the first."

Uses the dataset's explicitly correlated pair:
  1st: GUIDE-TP-002   (WS-FINANCE-07, j.khan, encoded PowerShell, IOC 198.51.100.78)
  2nd: GUIDE-TP-002-B (WS-FINANCE-12, a.malik, SAME encoded command, SAME IOC)

Flow:
  A. Clean both alerts/cases/memory records
  B. Run TP-002 through the full dual-agent flow -> case closes ->
     memory record written (checks DB + qoder_memory_record_id)
  C. Unit check: retrieve_similar_cases for TP-002-B's payload returns
     TP-002's record (deterministic, before any agent runs)
  D. Run TP-002-B through the full flow -> primary AND secondary prompts
     include the retrieved record -> agent responses reference the first
     alert (searches for TP-002 / WS-FINANCE-07 / prior-case language)
  E. Second memory record written

PASS requires: record written for #1, retrieval finds it, and at least one
agent's response on #2 explicitly references the first investigation.
"""

import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.db.supabase_client import get_supabase

BASE = "http://127.0.0.1:8000"
FIRST, SECOND = "GUIDE-TP-002", "GUIDE-TP-002-B"

# Terms that count as "referencing the first investigation"
REFERENCE_TERMS = ["GUIDE-TP-002", "TP-002", "WS-FINANCE-07", "j.khan"]


def load_alerts() -> dict:
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "sample_alerts.json",
    )
    with open(data_path, encoding="utf-8") as f:
        return {a["source_alert_id"]: a for a in json.load(f)}


def cleanup(sb) -> None:
    for sid in (FIRST, SECOND):
        rows = sb.table("alerts").select("id").eq("source_alert_id", sid).execute()
        for row in rows.data:
            sb.table("memory_records").delete().eq("alert_id", row["id"]).execute()
            sb.table("cases").delete().eq("alert_id", row["id"]).execute()
            sb.table("alerts").delete().eq("id", row["id"]).execute()
        if rows.data:
            print(f"  cleaned prior {sid} row(s)")


def run_flow(sb, sid: str, alerts_by_sid: dict) -> dict:
    """Ingest + full dual-agent flow for one alert. Returns response dict."""
    r = requests.post(f"{BASE}/alerts/", json=alerts_by_sid[sid], timeout=30)
    if r.status_code != 201:
        print(f"  FATAL: ingest {sid}: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    aid = r.json()["id"]
    print(f"  {sid} ingested ({aid[:8]})")

    t0 = time.time()
    r = requests.post(f"{BASE}/alerts/{aid}/reinvestigate", timeout=400)
    if r.status_code == 502:
        print("  502, retrying once in 5s...")
        time.sleep(5)
        r = requests.post(f"{BASE}/alerts/{aid}/reinvestigate", timeout=400)
    if r.status_code != 200:
        print(f"  FATAL: reinvestigate {sid}: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    data = r.json()
    print(f"  dual-agent flow completed in {time.time()-t0:.0f}s")
    return data


def main() -> int:
    print("=" * 70)
    print("Phase 11 — Memory Store + Case Retrieval + Learning")
    print("=" * 70)

    r = requests.get(f"{BASE}/health", timeout=15)
    if r.status_code != 200:
        print(f"FATAL: server not healthy: {r.status_code}")
        return 1
    print("\n[1] Server healthy")

    sb = get_supabase()
    alerts_by_sid = load_alerts()

    # A. Clean
    print("\n[2] Cleaning prior state...")
    cleanup(sb)

    # B. First alert: full flow -> memory record written
    print(f"\n[3] FIRST ALERT: {FIRST} — full dual-agent flow")
    first = run_flow(sb, FIRST, alerts_by_sid)
    print(f"  primary={first['primary']['verdict']} ({first['primary']['confidence']})  "
          f"secondary={first.get('secondary_verdict')} ({first['secondary']['confidence']})")
    print(f"  action: {first['action']['action_id']} / {first['action']['action_status']}  "
          f"case_closed={first['action']['case_closed']}")

    first_memory_id = first["action"].get("memory_record_id")
    checks_b = {
        "first case closed": first["action"]["case_closed"],
        "memory_record_id in API response": bool(first_memory_id),
        "primary saw no similar cases (memory was empty)": (
            not first["primary"].get("similar_cases")
        ),
    }

    # DB-level: record exists + case points at it
    mem_rows = (
        sb.table("memory_records").select("*").eq("source_alert_id", FIRST).execute()
    )
    db_mem_id = mem_rows.data[0]["id"] if mem_rows.data else None
    case_rows = (
        sb.table("cases").select("id, qoder_memory_record_id, closed_at")
        .eq("alert_id", first["alert_id"]).execute()
    )
    checks_b["memory record row in DB"] = bool(db_mem_id)
    checks_b["case.qoder_memory_record_id set"] = bool(
        case_rows.data and case_rows.data[0]["qoder_memory_record_id"]
    )
    if mem_rows.data:
        rec = mem_rows.data[0]
        print(f"  memory record {rec['id'][:8]}: verdict={rec['verdict']} "
              f"conf={rec['confidence']} technique={rec['attack_technique']} "
              f"iocs={rec['iocs']} mode={rec['mode']}")
        checks_b["record has evidence + action"] = bool(
            rec.get("evidence_gathered") and rec.get("response_taken")
        )
    for name, ok in checks_b.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")

    # C. Unit: retrieval finds the first record for the second alert
    print(f"\n[4] UNIT: retrieve_similar_cases for {SECOND}'s payload")
    from app.services.investigation import retrieve_similar_cases

    second_payload = alerts_by_sid[SECOND]["raw_payload"]
    similar = retrieve_similar_cases(
        "suspicious_process_execution", second_payload,
        exclude_source_alert_id=SECOND,
    )
    print(f"  retrieved {len(similar)} similar case(s)")
    for s in similar:
        print(f"    - {s['source_alert_id']} (score={s['similarity_score']}, "
              f"verdict={s['verdict']}, action={s['action_taken']})")
    checks_c = {
        "retrieval found the first case": any(
            s["source_alert_id"] == FIRST for s in similar
        ),
        "retrieval is not the alert itself": all(
            s["source_alert_id"] != SECOND for s in similar
        ),
    }
    for name, ok in checks_c.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")

    # D. Second alert: full flow with memory
    print(f"\n[5] SECOND ALERT: {SECOND} — full dual-agent flow (with memory)")
    second = run_flow(sb, SECOND, alerts_by_sid)
    print(f"  primary={second['primary']['verdict']} ({second['primary']['confidence']})  "
          f"secondary={second.get('secondary_verdict')} ({second['secondary']['confidence']})")

    p_similar = second["primary"].get("similar_cases") or []
    s_similar = second["secondary"].get("similar_cases") or []
    print(f"  primary prompt retrieved: {[s['source_alert_id'] for s in p_similar]}")
    print(f"  secondary prompt retrieved: {[s['source_alert_id'] for s in s_similar]}")

    checks_d = {
        "primary prompt included first case": any(
            s["source_alert_id"] == FIRST for s in p_similar
        ),
        "secondary prompt included first case": any(
            s["source_alert_id"] == FIRST for s in s_similar
        ),
    }

    # Does either agent's response reference the first investigation?
    p_resp = (second["primary"].get("agent_response") or "").lower()
    s_resp = (second["secondary"].get("agent_response") or "").lower()
    p_refs = [t for t in REFERENCE_TERMS if t.lower() in p_resp]
    s_refs = [t for t in REFERENCE_TERMS if t.lower() in s_resp]
    print(f"  primary response references: {p_refs or '—'}")
    print(f"  secondary response references: {s_refs or '—'}")
    checks_d["an agent response references the first case"] = bool(p_refs or s_refs)

    # E. Second record written
    mem2 = (
        sb.table("memory_records").select("id").eq("source_alert_id", SECOND).execute()
    )
    checks_d["second memory record written"] = bool(mem2.data)
    for name, ok in checks_d.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")

    # Summary
    all_checks = {**checks_b, **checks_c, **checks_d}
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    passed = sum(1 for ok in all_checks.values() if ok)
    for name, ok in all_checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("-" * 60)
    print(f"{passed}/{len(all_checks)} checks passed")

    core_met = (
        checks_b["memory record row in DB"]
        and checks_c["retrieval found the first case"]
        and checks_d["an agent response references the first case"]
    )
    if passed == len(all_checks):
        print("\nVERIFY CONDITION MET: two similar alerts in sequence —")
        print("the second investigation references the first.")
        return 0
    if core_met:
        print("\nVERIFY CONDITION MET (core): second alert references first;")
        print(f"{len(all_checks) - passed} auxiliary check(s) failed.")
        return 0
    print("\nVERIFY CONDITION NOT MET.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
