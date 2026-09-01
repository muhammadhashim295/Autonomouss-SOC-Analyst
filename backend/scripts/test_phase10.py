"""Phase 10 verification — impact classification + standard-action execution.

Verify condition (phases.md): "agentic-mode TP produces a logged,
documented action."

Three scenarios exercising the full decision matrix (existing GUIDE alerts):

1. GUIDE-TP-001 (brute force, OTX-flagged IOC, standard impact)
   → agentic-mode TP with agent agreement: block_ip EXECUTED, case closed,
     action logged on the case row.

2. GUIDE-HI-001 (data exfiltration from SRV-DC-01, 500 MB)
   → high_impact classification (enforced logic): NO execution, status
     awaiting_approval, case stays open for an analyst.

3. GUIDE-FP-001 (scheduled vulnerability scan)
   → cross-checked false_positive: no action, case closed.

Also verifies the action decision function directly (unit-level) for
approval-mode and disagreement branches that are expensive to reach E2E.
"""

import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.db.supabase_client import get_supabase

BASE = "http://127.0.0.1:8000"

SCENARIOS = [
    {
        "sid": "GUIDE-TP-001",
        "file": "GUIDE-TP-001",
        "expect_action_status": "executed",
        "expect_executed": True,
        "expect_case_closed": True,
        "description": "agentic TP + OTX-flagged IOC → block_ip executed",
    },
    {
        "sid": "GUIDE-HI-001",
        "file": "GUIDE-HI-001",
        "expect_action_status": "awaiting_approval",
        "expect_executed": False,
        "expect_case_closed": False,
        "description": "high_impact (data_exfiltration, SRV-DC-01) → human-gated",
    },
    {
        "sid": "GUIDE-FP-001",
        "file": "GUIDE-FP-001",
        "expect_action_status": "none",
        "expect_executed": False,
        "expect_case_closed": True,
        "description": "cross-checked FP → close, no action",
    },
]


def load_alerts() -> dict:
    """Load the three GUIDE alerts from sample_alerts.json."""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "sample_alerts.json",
    )
    import json
    with open(data_path, encoding="utf-8") as f:
        alerts = json.load(f)
    return {a["source_alert_id"]: a for a in alerts}


def cleanup(sb, sids: list[str]) -> None:
    for sid in sids:
        rows = sb.table("alerts").select("id").eq("source_alert_id", sid).execute()
        for row in rows.data:
            sb.table("cases").delete().eq("alert_id", row["id"]).execute()
            sb.table("alerts").delete().eq("id", row["id"]).execute()


def unit_check_decisions() -> list[tuple[str, bool, str]]:
    """Directly exercise decide_action for branches too costly to hit E2E."""
    from app.services.actions import decide_action

    checks: list[tuple[str, bool, str]] = []

    # Approval mode pauses a confident standard TP
    d = decide_action(
        primary_verdict="true_positive", secondary_verdict="agree",
        secondary_confidence=0.95, impact_level="standard", mode="approval",
        alert_type="brute_force_login", payload={},
    )
    checks.append((
        "approval mode pauses standard TP",
        d["action_status"] == "awaiting_approval" and not d["execute"],
        f"got {d['action_status']}",
    ))

    # Agents disagree → escalated, never executed
    d = decide_action(
        primary_verdict="false_positive", secondary_verdict="disagree",
        secondary_confidence=0.9, impact_level="standard", mode="agentic",
        alert_type="brute_force_login", payload={"user": "svc-backup"},
    )
    checks.append((
        "agent disagreement escalates (disable_account suggested)",
        d["action_status"] == "escalated" and not d["execute"]
        and d["action_id"] == "disable_account" and d["target"] == "svc-backup",
        f"got {d['action_status']}/{d['action_id']}/{d['target']}",
    ))

    # High-impact overrides approval-mode pause? No — always awaiting_approval
    d = decide_action(
        primary_verdict="true_positive", secondary_verdict="agree",
        secondary_confidence=0.99, impact_level="high_impact", mode="agentic",
        alert_type="suspicious_process_execution",
        payload={"hostname": "WS-FINANCE-07"},
    )
    checks.append((
        "high_impact always human-gated even at 0.99 confidence",
        d["action_status"] == "awaiting_approval" and not d["execute"]
        and d["action_id"] == "isolate_host" and d["target"] == "WS-FINANCE-07",
        f"got {d['action_status']}/{d['action_id']}/{d['target']}",
    ))

    # Low-confidence TP → flag_for_review (documented, no system change)
    d = decide_action(
        primary_verdict="true_positive", secondary_verdict="agree",
        secondary_confidence=0.55, impact_level="standard", mode="agentic",
        alert_type="port_scan", payload={},
    )
    checks.append((
        "low-confidence TP → flag_for_review, no system change",
        d["action_status"] == "executed" and d["execute"]
        and d["action_id"] == "flag_for_review",
        f"got {d['action_status']}/{d['action_id']}",
    ))

    return checks


def main() -> int:
    print("=" * 70)
    print("Phase 10 — Impact Classification + Standard-Action Execution")
    print("=" * 70)

    # 0. Unit-level decision checks first (fast, no agents involved)
    print("\n[0] Unit checks — decide_action rule cascade")
    all_pass = True
    for name, ok, detail in unit_check_decisions():
        status = "PASS" if ok else "FAIL"
        all_pass &= ok
        print(f"  [{status}] {name}" + ("" if ok else f"  ({detail})"))
    if not all_pass:
        print("\nUnit checks failed — aborting E2E run.")
        return 1

    # 1. Health check
    r = requests.get(f"{BASE}/health", timeout=15)
    if r.status_code != 200:
        print(f"FATAL: server not healthy: {r.status_code}")
        return 1
    print("\n[1] Server healthy")

    sb = get_supabase()
    alerts_by_sid = load_alerts()
    sids = [s["sid"] for s in SCENARIOS]

    # 2. Clean prior runs
    print("\n[2] Cleaning prior GUIDE alert/case rows...")
    cleanup(sb, sids)

    # 3. Ingest
    print("\n[3] Ingesting scenario alerts...")
    alert_ids = {}
    for sid in sids:
        r = requests.post(f"{BASE}/alerts/", json=alerts_by_sid[sid], timeout=30)
        if r.status_code != 201:
            print(f"  FATAL: ingest {sid} failed: {r.status_code} {r.text[:200]}")
            return 1
        alert_ids[sid] = r.json()["id"]
        print(f"  {sid}: ingested ({alert_ids[sid][:8]})")

    # 4. Run each scenario through the dual-agent + action pipeline
    results = []
    for sc in SCENARIOS:
        sid = sc["sid"]
        aid = alert_ids[sid]
        print(f"\n{'─' * 70}")
        print(f"SCENARIO: {sid} — {sc['description']}")
        print(f"{'─' * 70}")
        print("  running dual-agent flow + action pipeline (1-3 min)...")

        t0 = time.time()
        r = requests.post(f"{BASE}/alerts/{aid}/reinvestigate", timeout=400)
        if r.status_code == 502:
            print("  502 from server, retrying once in 5s...")
            time.sleep(5)
            r = requests.post(f"{BASE}/alerts/{aid}/reinvestigate", timeout=400)
        elapsed = time.time() - t0
        if r.status_code != 200:
            print(f"  ERROR {r.status_code}: {r.text[:300]}")
            results.append({**sc, "error": r.text[:200]})
            continue

        data = r.json()
        action = data["action"]
        pv = data["primary"]["verdict"]
        sv = data.get("secondary_verdict")
        sc_conf = data["secondary"]["confidence"]

        print(f"  completed in {elapsed:.0f}s")
        print(f"  primary={pv}  secondary={sv} ({sc_conf})")
        print(
            f"  ACTION: id={action['action_id']}  class={action['action_class']}  "
            f"status={action['action_status']}  target={action['target']}"
        )
        print(f"  executed={action['executed']}  case_closed={action['case_closed']}")
        print(f"  rationale: {action['rationale']}")

        # Verify against the case row in Supabase (the durable record)
        case_rows = (
            sb.table("cases")
            .select("id, action_status, action_taken, closed_at, impact_level")
            .eq("alert_id", aid)
            .execute()
        )
        case_ok = bool(case_rows.data)
        if case_ok:
            c = case_rows.data[0]
            print(
                f"  DB case: impact={c['impact_level']}  action_status={c['action_status']}  "
                f"closed_at={'set' if c['closed_at'] else 'None'}  "
                f"action_taken={'logged' if c['action_taken'] else 'None'}"
            )
            if c["action_taken"]:
                import json as _json
                rec = _json.loads(c["action_taken"])
                print(
                    f"  DB record: action={rec.get('action')}  result={rec.get('result')}  "
                    f"simulated={rec.get('simulated')}  executed_at={rec.get('executed_at', '')[:19]}"
                )

        # Alert status check
        alert_rows = sb.table("alerts").select("status").eq("id", aid).execute()
        alert_status = alert_rows.data[0]["status"] if alert_rows.data else "?"
        print(f"  alert status: {alert_status}")

        checks = {
            "action_status matches expectation": (
                action["action_status"] == sc["expect_action_status"]
            ),
            "executed flag matches": action["executed"] == sc["expect_executed"],
            "case closure matches": action["case_closed"] == sc["expect_case_closed"],
            "case row updated in DB": case_ok and case_rows.data[0][
                "action_status"
            ] == sc["expect_action_status"],
            "closed_at set iff case closed": case_ok and (
                bool(case_rows.data[0]["closed_at"]) == sc["expect_case_closed"]
            ),
            "action_taken logged iff action decided": case_ok and (
                bool(case_rows.data[0]["action_taken"])
                == (sc["expect_action_status"] != "none")
            ),
            "alert status mirrors case": (
                alert_status == ("closed" if sc["expect_case_closed"] else "in_review")
            ),
        }
        for name, ok in checks.items():
            print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
        results.append({**sc, "passed": all(checks.values())})

    # 5. Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'Alert':<15} {'Expected status':<20} {'Result'}")
    print("-" * 60)
    for res in results:
        if "error" in res:
            print(f"{res['sid']:<15} {res['expect_action_status']:<20} ERROR: {res['error'][:40]}")
        else:
            print(
                f"{res['sid']:<15} {res['expect_action_status']:<20} "
                f"{'PASS' if res['passed'] else 'FAIL'}"
            )
    print("-" * 60)

    passed = sum(1 for r in results if r.get("passed"))
    failed = len(results) - passed
    print(f"Unit checks: 4/4 PASS   E2E scenarios: {passed}/{len(results)} PASS")

    if failed == 0:
        print("\nVERIFY CONDITION MET: agentic-mode TP produces a logged,")
        print("documented action; high-impact always awaits approval; FP closes.")
        return 0
    print(f"\nVERIFY CONDITION NOT MET: {failed} scenario(s) failed.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
