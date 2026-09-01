"""Re-verify the corrected action_taken assertion against persisted rows.

The Phase 10 E2E run already validated everything except one assertion that
was wrong in the test itself (awaiting_approval cases DO log the suggested
action record — required by the escalation screen design).  This script
re-checks all scenario expectations against the durable case/alert rows.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from app.db.supabase_client import get_supabase

EXPECTATIONS = {
    "GUIDE-TP-001": {"action_status": "executed", "closed": True, "alert": "closed",
                     "record_result": "blocked", "record_action": "block_ip"},
    "GUIDE-HI-001": {"action_status": "awaiting_approval", "closed": False, "alert": "in_review",
                     "record_result": "not_executed", "record_action": "isolate_host"},
    "GUIDE-FP-001": {"action_status": "none", "closed": True, "alert": "closed",
                     "record_result": None, "record_action": None},
}

sb = get_supabase()
all_pass = True

for sid, exp in EXPECTATIONS.items():
    rows = (
        sb.table("alerts").select("id, status").eq("source_alert_id", sid).execute()
    )
    if not rows.data:
        print(f"[FAIL] {sid}: alert row missing")
        all_pass = False
        continue
    alert = rows.data[0]
    cases = (
        sb.table("cases")
        .select("id, action_status, action_taken, closed_at, impact_level")
        .eq("alert_id", alert["id"])
        .execute()
    )
    if not cases.data:
        print(f"[FAIL] {sid}: case row missing")
        all_pass = False
        continue
    c = cases.data[0]
    record = json.loads(c["action_taken"]) if c["action_taken"] else None

    checks = {
        "action_status": c["action_status"] == exp["action_status"],
        "closed_at set/clear": bool(c["closed_at"]) == exp["closed"],
        "alert status": alert["status"] == exp["alert"],
        "action_taken logged iff decided": bool(c["action_taken"]) == (exp["action_status"] != "none"),
    }
    if record:
        checks["record action id"] = record.get("action") == exp["record_action"]
        checks["record result"] = record.get("result") == exp["record_result"]
        checks["record simulated flag"] = record.get("simulated") is True
        checks["record has executed_at"] = bool(record.get("executed_at"))
        checks["record has rationale"] = bool(record.get("reason"))

    ok = all(checks.values())
    all_pass &= ok
    print(f"{'[PASS]' if ok else '[FAIL]'} {sid}  (action_status={c['action_status']}, impact={c['impact_level']})")
    for name, passed in checks.items():
        if not passed:
            print(f"         ↳ FAIL: {name}")

print()
if all_pass:
    print("ALL SCENARIOS VERIFIED — Phase 10 verify condition met:")
    print("agentic-mode TP produces a logged, documented action; high-impact")
    print("always awaits approval; FP closes with no action.")
    sys.exit(0)
print("SOME CHECKS FAILED")
sys.exit(2)
