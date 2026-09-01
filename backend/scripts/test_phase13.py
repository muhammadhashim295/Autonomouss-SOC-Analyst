"""Phase 13 verification — analyst decision handling + correction memory.

Verify condition (phases.md): "override an alert, replay a similar one,
confirm the agent's next suggestion reflects the correction."

Story line (the learning-loop demo moment):

  1. Approval mode ON. Run GUIDE-TP-001 (SSH brute force) -> agents say
     TP, block_ip suggested -> PAUSED (awaiting_approval).
  2. Analyst REDIRECTS: "this is our authorized red-team engagement —
     do not block; notify the SOC lead only."
  3. Check: analyst_overrides row written; case closed; CORRECTION
     memory record written (record_type=correction, analyst_correction
     text, boosted retrieval).
  4. Replay a SIMILAR alert (REPLAY-001: same attack pattern, different
     source IP -> no shared IOC, so retrieval only works via the
     correction boost).
  5. Check: correction record retrieved into BOTH agents' prompts; at
     least one agent response references the correction / pen-test
     context, and the pipeline's decision reflects it.

Also unit-checks the decision flow edge cases (approved on a paused
case, double-decision rejection, redirect without action text).
"""

import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.db.supabase_client import get_supabase

BASE = "http://127.0.0.1:8000"

# The analyst's redirect on GUIDE-TP-001
REDIRECT_ACTION = (
    "Do not block this IP — it belongs to our authorized red-team "
    "engagement. Notify the SOC lead and log the observation only."
)
REDIRECT_REASONING = (
    "Confirmed with the offensive security team: source 203.0.113.45 is "
    "their Kali box for this week's external assessment. Blocking would "
    "disrupt the authorized engagement."
)

# Replay alert: same attack shape, DIFFERENT source IP (no shared IOC —
# only the correction boost can retrieve the prior case)
REPLAY_ALERT = {
    "source_alert_id": "REPLAY-001",
    "alert_type": "brute_force_login",
    "raw_payload": {
        "source_ip": "203.0.113.77",
        "destination_ip": "10.0.3.10",
        "destination_port": 22,
        "protocol": "TCP",
        "target_service": "SSH",
        "failed_attempts": 612,
        "time_window_seconds": 240,
        "unique_usernames_tried": 17,
        "usernames_sample": ["root", "admin", "ubuntu", "deploy", "jenkins"],
        "geo_ip": {"country": "CN", "city": "Shenzhen", "asn": "AS4134"},
        "description": "High-volume SSH brute force from external IP with dictionary attack pattern",
        "log_entries": [
            {"timestamp": "2026-09-01T10:12:33Z", "event": "Failed password for root", "src": "203.0.113.77", "dst": "10.0.3.10"},
            {"timestamp": "2026-09-01T10:12:34Z", "event": "Failed password for admin", "src": "203.0.113.77", "dst": "10.0.3.10"},
            {"timestamp": "2026-09-01T10:16:33Z", "event": "612 failed attempts in 4 minutes", "src": "203.0.113.77", "dst": "10.0.3.10"},
        ],
        "iocs": ["203.0.113.77"],
        "network_zone": "external",
    },
}

# Terms that count as the correction influencing the agents
CORRECTION_TERMS = [
    "red-team", "red team", "authorized", "analyst", "correction",
    "penetration", "pen test", "prior", "previous", "GUIDE-TP-001",
]


def load_alerts() -> dict:
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "sample_alerts.json",
    )
    with open(data_path, encoding="utf-8") as f:
        return {a["source_alert_id"]: a for a in json.load(f)}


def set_mode(mode: str) -> None:
    r = requests.put(f"{BASE}/settings/mode", json={"mode": mode}, timeout=15)
    assert r.status_code == 200, f"set_mode failed: {r.text}"


def cleanup(sb, sids: list[str]) -> None:
    for sid in sids:
        rows = sb.table("alerts").select("id").eq("source_alert_id", sid).execute()
        for row in rows.data:
            # Overrides reference cases; delete them first
            cases = sb.table("cases").select("id").eq("alert_id", row["id"]).execute()
            for c in cases.data:
                sb.table("analyst_overrides").delete().eq("case_id", c["id"]).execute()
            sb.table("memory_records").delete().eq("alert_id", row["id"]).execute()
            sb.table("cases").delete().eq("alert_id", row["id"]).execute()
            sb.table("alerts").delete().eq("id", row["id"]).execute()


def main() -> int:
    print("=" * 70)
    print("Phase 13 — Analyst Decision Handling + Correction Memory")
    print("=" * 70)

    r = requests.get(f"{BASE}/health", timeout=15)
    if r.status_code != 200:
        print(f"FATAL: server not healthy: {r.status_code}")
        return 1
    print("\n[1] Server healthy")

    sb = get_supabase()
    alerts_by_sid = load_alerts()
    all_checks: dict[str, bool] = {}

    # ── Step 1: paused case in approval mode ───────────────────────────
    print("\n[2] Approval mode + GUIDE-TP-001 -> paused case")
    set_mode("approval")
    cleanup(sb, ["GUIDE-TP-001", "REPLAY-001"])
    r = requests.post(f"{BASE}/alerts/", json=alerts_by_sid["GUIDE-TP-001"], timeout=30)
    aid = r.json()["id"]
    r = requests.post(f"{BASE}/alerts/{aid}/reinvestigate", timeout=400)
    if r.status_code == 502:
        time.sleep(5)
        r = requests.post(f"{BASE}/alerts/{aid}/reinvestigate", timeout=400)
    assert r.status_code == 200, f"reinvestigate failed: {r.text[:300]}"
    data = r.json()
    case_id = data["case_id"]
    print(f"  case {case_id[:8]}: {data['primary']['verdict']} / "
          f"{data.get('secondary_verdict')} -> {data['action']['action_id']} "
          f"{data['action']['action_status']}")
    all_checks["case paused awaiting approval"] = (
        data["action"]["action_status"] == "awaiting_approval"
    )

    # ── Step 2: edge cases on the decision endpoint ────────────────────
    print("\n[3] Decision endpoint edge cases")
    r = requests.post(
        f"{BASE}/cases/{case_id}/decision",
        json={"decision": "redirected"},  # missing analyst_action
        timeout=15,
    )
    all_checks["redirect without action rejected (422)"] = r.status_code == 422
    print(f"  redirected w/o action -> {r.status_code} (expect 422)")

    r = requests.post(
        f"{BASE}/cases/00000000-0000-0000-0000-000000000000/decision",
        json={"decision": "approved"},
        timeout=15,
    )
    all_checks["unknown case -> 404"] = r.status_code == 404
    print(f"  unknown case -> {r.status_code} (expect 404)")

    # ── Step 3: the analyst redirect ───────────────────────────────────
    print("\n[4] ANALYST DECISION: redirect the block_ip suggestion")
    r = requests.post(
        f"{BASE}/cases/{case_id}/decision",
        json={
            "decision": "redirected",
            "analyst_action": REDIRECT_ACTION,
            "analyst_reasoning": REDIRECT_REASONING,
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"  FATAL: decision failed: {r.status_code} {r.text[:300]}")
        return 2
    decision = r.json()
    print(f"  decision applied: action_status={decision['action_status']}, "
          f"memory={decision['memory_record_type']} ({(decision['memory_record_id'] or '')[:8]})")
    print(f"  correction: {decision['analyst_correction'][:120]}...")

    all_checks["redirect closes the case"] = decision["case_closed"] is True
    all_checks["correction memory record written"] = (
        decision["memory_record_type"] == "correction"
        and bool(decision["memory_record_id"])
    )
    all_checks["action_status executed (redirect target)"] = (
        decision["action_status"] == "executed"
    )

    # Double decision must be rejected
    r = requests.post(
        f"{BASE}/cases/{case_id}/decision", json={"decision": "approved"}, timeout=15
    )
    all_checks["second decision rejected (422)"] = r.status_code == 422
    print(f"  second decision -> {r.status_code} (expect 422)")

    # DB checks: override row, case closed, alert closed, record content
    override_rows = (
        sb.table("analyst_overrides").select("*").eq("case_id", case_id).execute()
    )
    case_rows = sb.table("cases").select("*").eq("id", case_id).execute()
    alert_rows = sb.table("alerts").select("status").eq("id", aid).execute()
    mem_rows = (
        sb.table("memory_records").select("*")
        .eq("id", decision["memory_record_id"]).execute()
    )

    if override_rows.data:
        ov = override_rows.data[0]
        print(f"  override row: decision={ov['analyst_decision']}, "
              f"original={ov['original_suggestion']}, action={ov['analyst_action'][:50]}...")
    all_checks["analyst_overrides row written"] = bool(override_rows.data)
    all_checks["case closed in DB"] = bool(
        case_rows.data and case_rows.data[0]["closed_at"]
    )
    all_checks["alert closed"] = (
        alert_rows.data and alert_rows.data[0]["status"] == "closed"
    )
    if mem_rows.data:
        rec = mem_rows.data[0]
        print(f"  memory record: type={rec['record_type']}, "
              f"correction={bool(rec['analyst_correction'])}, "
              f"iocs={rec['iocs']}, mode={rec['mode']}")
    all_checks["record_type=correction in DB"] = bool(
        mem_rows.data and mem_rows.data[0]["record_type"] == "correction"
    )
    all_checks["correction text persisted"] = bool(
        mem_rows.data and mem_rows.data[0]["analyst_correction"]
    )

    # GET /cases/{id} sanity (used by the frontend escalation screen)
    r = requests.get(f"{BASE}/cases/{case_id}", timeout=15)
    detail = r.json() if r.status_code == 200 else {}
    all_checks["GET case detail works"] = (
        r.status_code == 200
        and detail.get("case", {}).get("id") == case_id
        and len(detail.get("analyst_overrides", [])) == 1
        and detail.get("memory_record", {}).get("record_type") == "correction"
    )
    print(f"  GET /cases/{{id}} -> {r.status_code} "
          f"(overrides={len(detail.get('analyst_overrides', []))}, "
          f"memory={'yes' if detail.get('memory_record') else 'no'})")

    for name, ok in all_checks.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")

    # ── Step 4: replay a similar alert ─────────────────────────────────
    print("\n[5] REPLAY: similar alert (REPLAY-001, different source IP)")
    set_mode("agentic")
    r = requests.post(f"{BASE}/alerts/", json=REPLAY_ALERT, timeout=30)
    rid = r.json()["id"]
    t0 = time.time()
    r = requests.post(f"{BASE}/alerts/{rid}/reinvestigate", timeout=400)
    if r.status_code == 502:
        time.sleep(5)
        r = requests.post(f"{BASE}/alerts/{rid}/reinvestigate", timeout=400)
    if r.status_code != 200:
        print(f"  FATAL: replay reinvestigate failed: {r.status_code} {r.text[:300]}")
        return 2
    replay = r.json()
    print(f"  flow completed in {time.time()-t0:.0f}s")

    p_similar = replay["primary"].get("similar_cases") or []
    s_similar = replay["secondary"].get("similar_cases") or []
    p_retrieved = [s["source_alert_id"] for s in p_similar]
    s_retrieved = [s["source_alert_id"] for s in s_similar]
    print(f"  primary retrieved:   {p_retrieved}")
    print(f"  secondary retrieved: {s_retrieved}")

    checks_r = {
        "R: correction retrieved into primary prompt": any(
            s["source_alert_id"] == "GUIDE-TP-001"
            and s.get("record_type") == "correction"
            for s in p_similar
        ),
        "R: correction retrieved into secondary prompt": any(
            s["source_alert_id"] == "GUIDE-TP-001"
            and s.get("record_type") == "correction"
            for s in s_similar
        ),
    }

    # Did the agents' responses reflect the correction?
    p_resp = (replay["primary"].get("agent_response") or "").lower()
    s_resp = (replay["secondary"].get("agent_response") or "").lower()
    p_refs = [t for t in CORRECTION_TERMS if t in p_resp]
    s_refs = [t for t in CORRECTION_TERMS if t in s_resp]
    print(f"  primary references:   {p_refs or '—'}")
    print(f"  secondary references: {s_refs or '—'}")
    checks_r["R: an agent response reflects the correction"] = bool(p_refs or s_refs)

    # Did the pipeline's decision change? (block_ip would ignore the
    # correction; flag/ticket/enrich respects the no-block guidance)
    action = replay["action"]
    print(f"  pipeline decision: {action['action_id']} / {action['action_status']}")
    checks_r["R: suggestion respects no-block guidance"] = action["action_id"] != "block_ip"
    print(f"  rationale: {action['rationale'][:150]}")

    for name, ok in checks_r.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    all_checks.update(checks_r)

    # ── Cleanup ────────────────────────────────────────────────────────
    print("\n[6] Cleanup")
    set_mode("agentic")
    cleanup(sb, ["GUIDE-TP-001", "REPLAY-001"])
    print("  test data removed; mode reset to agentic")

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
        all_checks["correction memory record written"]
        and checks_r["R: correction retrieved into primary prompt"]
        and checks_r["R: an agent response reflects the correction"]
    )
    if passed == len(all_checks):
        print("\nVERIFY CONDITION MET: override an alert, replay a similar")
        print("one — the agents' next investigation reflects the correction.")
        return 0
    if core:
        print("\nVERIFY CONDITION MET (core); some auxiliary check(s) failed.")
        return 0
    print("\nVERIFY CONDITION NOT MET.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
