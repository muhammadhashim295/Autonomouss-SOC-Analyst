"""Phase 8 verification — Secondary Agent (Deep Investigation Agent).

Verify conditions:
1. Session created with the Secondary Agent
2. Secondary agent can read the Primary Agent's output
3. Produces an independent re-investigation with agree/disagree verdict

Uses GUIDE-TP-001 (clear true positive) — the primary already triaged it
as true_positive in Phase 7, so the secondary should independently
re-derive and (likely) agree.
"""

import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.db.supabase_client import get_supabase

BASE = "http://127.0.0.1:8000"
TARGET = "GUIDE-TP-001"

print("=" * 70)
print("Phase 8 — Secondary Agent Re-Investigation Test")
print("=" * 70)

# 1. Health check
r = requests.get(f"{BASE}/health")
if r.status_code != 200:
    print(f"FATAL: server not healthy: {r.status_code}")
    sys.exit(1)
print("\n[1] Server healthy")

# 2. Find the target alert
sb = get_supabase()
res = sb.table("alerts").select("*").eq("source_alert_id", TARGET).limit(1).execute()
if not res.data:
    print(f"FATAL: {TARGET} not found in alerts table")
    sys.exit(1)
alert = res.data[0]
alert_id = alert["id"]
print(f"[2] Found {TARGET}: {alert_id}")

# 3. Check for an existing case from Phase 7 triage
case_res = sb.table("cases").select("*").eq("alert_id", alert_id).limit(1).execute()
has_case = bool(case_res.data)
print(f"[3] Existing case: {'yes — ' + case_res.data[0]['id'][:8] if has_case else 'no'}")

# 4. Run the full re-investigation (primary chained inline if no case)
print("\n[4] Calling POST /alerts/{id}/reinvestigate ...")
print("    (this runs Primary if needed, then Secondary — may take 2-4 min)")
t0 = time.time()
r = requests.post(
    f"{BASE}/alerts/{alert_id}/reinvestigate",
    json={} if not has_case else None,
    timeout=400,
)
elapsed = time.time() - t0

if r.status_code != 200:
    print(f"    ERROR {r.status_code}: {r.text[:300]}")
    sys.exit(1)

data = r.json()
print(f"    Completed in {elapsed:.0f}s")

# 5. Verify conditions
print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

primary = data.get("primary", {})
secondary = data.get("secondary", {})

print(f"\n[5] Primary Agent (ran now: {data.get('primary_ran_now')}):")
print(f"    Verdict:    {primary.get('verdict')}")
print(f"    Confidence: {primary.get('confidence')}")

print(f"\n[6] Secondary Agent (session: {secondary.get('session_id')}):")
print(f"    Verdict:            {data.get('secondary_verdict')}")
print(f"    Confidence:         {secondary.get('confidence')}")
print(f"    Impact level:       {secondary.get('impact_level')}")

reasoning = secondary.get("reasoning", "")
if reasoning:
    print(f"\n    REASONING (first 600 chars):")
    for line in reasoning[:600].split("\n"):
        if line.strip():
            print(f"      {line.strip()}")

# Check the secondary's response references the primary's report
agent_response = secondary.get("agent_response", "")
references_primary = any(
    kw in agent_response.lower()
    for kw in ["primary", "cross-check", "agree", "disagree"]
)
print(f"\n[7] Secondary references primary's output: {'PASS' if references_primary else 'FAIL'}")

# Check verdict is one of the valid values
sv = data.get("secondary_verdict")
valid_verdict = sv in ("agree", "disagree", "false_positive", "true_positive")
print(f"[8] Secondary verdict valid ({sv}): {'PASS' if valid_verdict else 'FAIL'}")

# 9. Check the case was updated in Supabase
case_id = data.get("case_id")
case_check = sb.table("cases").select("*").eq("id", case_id).execute()
if case_check.data:
    stored_sv = case_check.data[0].get("secondary_verdict")
    print(f"[9] Case updated in Supabase (secondary_verdict={stored_sv}): "
          f"{'PASS' if stored_sv == sv else 'FAIL'}")
else:
    print(f"[9] Case updated in Supabase: FAIL (case not found)")

# 10. Did the secondary cite independent evidence?
has_evidence = any(
    kw in reasoning.lower()
    for kw in ["otx", "attack", "correlation", "deviation", "log"]
)
print(f"[10] Secondary cites independent evidence: {'PASS' if has_evidence else 'FAIL'}")

print("\n" + "=" * 70)
print("PHASE 8 TEST COMPLETE")
print("=" * 70)
