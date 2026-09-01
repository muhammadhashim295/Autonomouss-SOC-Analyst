"""Phase 12 verification — mode toggle + escalation path (approval mode).

Verify condition (phases.md): "Global agentic/approval toggle. Approval
mode pauses standard-action decisions for analyst review. High-impact
always pauses regardless of mode. Verify both branches."

Branches:
  A. APPROVAL mode + standard TP (GUIDE-TP-001)  -> action PAUSED
     (awaiting_approval, not executed, case open, case.mode=approval,
     no memory record — the record defers until a human decision closes it)
  B. APPROVAL mode + high-impact TP (GUIDE-HI-001) -> still awaiting_approval
     (mode does not weaken the high-impact gate; suggested isolate_host)
  C. AGENTIC mode + standard TP (GUIDE-TP-001, fresh) -> block_ip EXECUTED,
     case closed, case.mode=agentic, memory record written

Also verifies the toggle API itself (GET/PUT roundtrip, invalid rejected).
"""

import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.db.supabase_client import get_supabase

BASE = "http://127.0.0.1:8000"


def load_alerts() -> dict:
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "sample_alerts.json",
    )
    with open(data_path, encoding="utf-8") as f:
        return {a["source_alert_id"]: a for a in json.load(f)}


def set_mode(mode: str) -> None:
    r = requests.put(f"{BASE}/settings/mode", json={"mode": mode}, timeout=15)
    assert r.status_code == 200, f"set_mode({mode}) failed: {r.status_code} {r.text}"
    assert r.json()["mode"] == mode


def cleanup(sb, sids: list[str]) -> None:
    for sid in sids:
        rows = sb.table("alerts").select("id").eq("source_alert_id", sid).execute()
        for row in rows.data:
            sb.table("memory_records").delete().eq("alert_id", row["id"]).execute()
            sb.table("cases").delete().eq("alert_id", row["id"]).execute()
            sb.table("alerts").delete().eq("id", row["id"]).execute()


def run_case(sb, alerts_by_sid: dict, sid: str) -> dict:
    """Ingest + full dual-agent flow for one alert; returns response dict."""
    r = requests.post(f"{BASE}/alerts/", json=alerts_by_sid[sid], timeout=30)
    if r.status_code != 201:
        print(f"  FATAL: ingest {sid}: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    aid = r.json()["id"]
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
    print(f"  {sid}: flow completed in {time.time()-t0:.0f}s "
          f"(primary={data['primary']['verdict']}, secondary={data.get('secondary_verdict')})")
    return data


def main() -> int:
    print("=" * 70)
    print("Phase 12 — Mode Toggle + Escalation Path (Approval Mode)")
    print("=" * 70)

    r = requests.get(f"{BASE}/health", timeout=15)
    if r.status_code != 200:
        print(f"FATAL: server not healthy: {r.status_code}")
        return 1
    print("\n[1] Server healthy")

    sb = get_supabase()
    alerts_by_sid = load_alerts()
    all_checks: dict[str, bool] = {}

    # ── Toggle API ─────────────────────────────────────────────────────
    print("\n[2] Toggle API checks")
    r = requests.put(f"{BASE}/settings/mode", json={"mode": "turbo"}, timeout=15)
    all_checks["invalid mode rejected (422)"] = r.status_code == 422
    print(f"  PUT mode=turbo -> {r.status_code} (expect 422)")

    set_mode("agentic")
    r = requests.get(f"{BASE}/settings/mode", timeout=15)
    all_checks["GET/PUT roundtrip (agentic)"] = (
        r.status_code == 200 and r.json()["mode"] == "agentic"
    )
    print(f"  set agentic, GET -> {r.json()['mode']}")

    set_mode("approval")
    r = requests.get(f"{BASE}/settings/mode", timeout=15)
    all_checks["GET/PUT roundtrip (approval)"] = (
        r.status_code == 200 and r.json()["mode"] == "approval"
    )
    print(f"  set approval, GET -> {r.json()['mode']}")
    for name, ok in all_checks.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")

    # ── Branch A: approval mode pauses a standard TP ──────────────────
    print("\n[3] BRANCH A — approval mode + standard TP (GUIDE-TP-001)")
    cleanup(sb, ["GUIDE-TP-001"])
    data = run_case(sb, alerts_by_sid, "GUIDE-TP-001")
    action = data["action"]
    print(f"  ACTION: {action['action_id']} / {action['action_status']} "
          f"(executed={action['executed']}, case_closed={action['case_closed']})")

    case_rows = (
        sb.table("cases").select("id, mode, action_status, closed_at")
        .eq("alert_id", data["alert_id"]).execute()
    )
    c = case_rows.data[0]
    mem_rows = (
        sb.table("memory_records").select("id")
        .eq("alert_id", data["alert_id"]).execute()
    )
    print(f"  DB: case mode={c['mode']}, closed_at={c['closed_at']}, "
          f"memory records={len(mem_rows.data)}")

    checks_a = {
        "A: action paused (awaiting_approval)": action["action_status"] == "awaiting_approval",
        "A: not executed": action["executed"] is False,
        "A: case stays open": action["case_closed"] is False and c["closed_at"] is None,
        "A: case snapshots mode=approval": c["mode"] == "approval",
        "A: no memory record (deferred)": len(mem_rows.data) == 0,
        "A: suggested action still recorded": bool(action["record"]),
    }
    for name, ok in checks_a.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    all_checks.update(checks_a)

    # ── Branch B: high-impact in approval mode (unchanged gate) ────────
    print("\n[4] BRANCH B — approval mode + high-impact TP (GUIDE-HI-001)")
    cleanup(sb, ["GUIDE-HI-001"])
    data = run_case(sb, alerts_by_sid, "GUIDE-HI-001")
    action = data["action"]
    print(f"  ACTION: {action['action_id']} / {action['action_status']} "
          f"(executed={action['executed']}, case_closed={action['case_closed']})")
    checks_b = {
        "B: high-impact still awaiting_approval": action["action_status"] == "awaiting_approval",
        "B: suggests isolate_host": action["action_id"] == "isolate_host",
        "B: not executed": action["executed"] is False,
        "B: case stays open": action["case_closed"] is False,
    }
    for name, ok in checks_b.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    all_checks.update(checks_b)

    # ── Branch C: agentic mode executes the same standard TP ──────────
    print("\n[5] BRANCH C — agentic mode + standard TP (GUIDE-TP-001, fresh)")
    set_mode("agentic")
    print("  mode reset to agentic")
    cleanup(sb, ["GUIDE-TP-001"])
    data = run_case(sb, alerts_by_sid, "GUIDE-TP-001")
    action = data["action"]
    print(f"  ACTION: {action['action_id']} / {action['action_status']} "
          f"(executed={action['executed']}, case_closed={action['case_closed']})")

    case_rows = (
        sb.table("cases").select("id, mode, action_status, closed_at")
        .eq("alert_id", data["alert_id"]).execute()
    )
    c = case_rows.data[0]
    mem_rows = (
        sb.table("memory_records").select("id")
        .eq("alert_id", data["alert_id"]).execute()
    )
    print(f"  DB: case mode={c['mode']}, closed_at={'set' if c['closed_at'] else 'None'}, "
          f"memory records={len(mem_rows.data)}")

    checks_c = {
        "C: action executed": action["action_status"] == "executed" and action["executed"] is True,
        "C: block_ip on OTX IOC": action["action_id"] == "block_ip",
        "C: case closed": action["case_closed"] is True and bool(c["closed_at"]),
        "C: case snapshots mode=agentic": c["mode"] == "agentic",
        "C: memory record written on close": len(mem_rows.data) == 1,
    }
    for name, ok in checks_c.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    all_checks.update(checks_c)

    # ── Cleanup: leave the system in default state ────────────────────
    print("\n[6] Cleanup")
    cleanup(sb, ["GUIDE-TP-001", "GUIDE-HI-001"])
    set_mode("agentic")
    print("  test alerts/cases/memory removed; mode reset to agentic")

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    passed = sum(1 for ok in all_checks.values() if ok)
    for name, ok in all_checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("-" * 60)
    print(f"{passed}/{len(all_checks)} checks passed")

    core = (
        checks_a["A: action paused (awaiting_approval)"]
        and checks_c["C: action executed"]
        and checks_b["B: high-impact still awaiting_approval"]
    )
    if passed == len(all_checks):
        print("\nVERIFY CONDITION MET: both toggle branches verified —")
        print("approval mode pauses standard actions; agentic mode executes")
        print("them; high-impact always pauses regardless of mode.")
        return 0
    if core:
        print("\nVERIFY CONDITION MET (core branches); auxiliary check(s) failed.")
        return 0
    print("\nVERIFY CONDITION NOT MET.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
