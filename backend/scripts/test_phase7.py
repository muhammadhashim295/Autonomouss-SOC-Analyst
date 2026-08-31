"""Phase 7 test — full investigation flow on GUIDE-FP-001, TP-001, TP-002."""

import json
import sys
import requests

BASE = "http://localhost:8000"
TARGETS = ["GUIDE-FP-001", "GUIDE-TP-001", "GUIDE-TP-002"]

print("=" * 70)
print("Phase 7 — Full Investigation Flow Test")
print("=" * 70)

# 1. Find the target GUIDE alerts in the DB
r = requests.get(f"{BASE}/alerts/", params={"limit": 200})
all_alerts = r.json()

# Map source_alert_id -> first matching alert UUID
alert_map = {}
for a in all_alerts:
    sid = a["source_alert_id"]
    if sid in TARGETS and sid not in alert_map:
        alert_map[sid] = a["id"]

print(f"\nFound {len(alert_map)}/{len(TARGETS)} target alerts in DB:")
for sid, uid in alert_map.items():
    print(f"  {sid} -> {uid}")

# Seed missing alerts if needed
missing = [t for t in TARGETS if t not in alert_map]
if missing:
    print(f"\nSeeding {len(missing)} missing alerts...")
    import os
    sample_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "app", "data", "sample_alerts.json")
    with open(sample_path) as f:
        samples = json.load(f)
    for sample in samples:
        if sample["source_alert_id"] in missing:
            r = requests.post(f"{BASE}/alerts/", json=sample)
            if r.status_code == 201:
                aid = r.json()["id"]
                alert_map[sample["source_alert_id"]] = aid
                print(f"  Seeded {sample['source_alert_id']} -> {aid}")

print(f"\n{'=' * 70}")
print(f"Running triage on {len(alert_map)} alerts...")
print(f"{'=' * 70}")

# 2. Run triage on each target
for source_id in TARGETS:
    if source_id not in alert_map:
        print(f"\n[SKIP] {source_id} not found in DB")
        continue

    alert_id = alert_map[source_id]
    print(f"\n{'─' * 70}")
    print(f"INVESTIGATING: {source_id} ({alert_id})")
    print(f"{'─' * 70}")

    r = requests.post(f"{BASE}/alerts/{alert_id}/triage", timeout=240)

    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:200]}")
        continue

    result = r.json()

    print(f"\n  Verdict:          {result.get('verdict', 'N/A')}")
    print(f"  Confidence:       {result.get('confidence', 'N/A')}")
    print(f"  Impact Level:     {result.get('impact_level', 'N/A')}")
    print(f"  ATT&CK Technique: {result.get('attack_technique', 'N/A')}")
    print(f"  Case ID:          {result.get('case_id', 'N/A')}")
    print(f"\n  REASONING:")
    reasoning = result.get("reasoning", "N/A")
    for line in reasoning.split("\n")[:10]:
        print(f"    {line.strip()}")
    print(f"\n  SELF-AUDIT:")
    self_audit = result.get("self_audit", "N/A")
    for line in self_audit.split("\n")[:5]:
        print(f"    {line.strip()}")

    # Check if reasoning cites evidence
    has_otx = any(kw in reasoning.lower() for kw in ["otx", "reputation", "ioc"])
    has_attack = any(kw in reasoning.lower() for kw in ["attack", "technique", "t1", "mitre"])
    has_corr = any(kw in reasoning.lower() for kw in ["correlation", "log", "sequence", "chain"])
    has_deviation = any(kw in reasoning.lower() for kw in ["deviation", "behavioral", "anomal", "off-hours"])
    citations = sum([has_otx, has_attack, has_corr, has_deviation])

    print(f"\n  EVIDENCE CITATIONS: {citations}/4 skills referenced")
    if has_otx:      print(f"    [x] OTX enrichment")
    else:            print(f"    [ ] OTX enrichment")
    if has_attack:   print(f"    [x] ATT&CK mapping")
    else:            print(f"    [ ] ATT&CK mapping")
    if has_corr:     print(f"    [x] Log correlation")
    else:            print(f"    [ ] Log correlation")
    if has_deviation: print(f"    [x] Behavioral deviation")
    else:             print(f"    [ ] Behavioral deviation")

print(f"\n{'=' * 70}")

# 3. Verify cases were persisted to Supabase
r = requests.get(f"{BASE}/alerts/", params={"limit": 200})
all_alerts = r.json()
triaged = [a for a in all_alerts if a["source_alert_id"] in TARGETS]
for a in triaged:
    status_icon = "closed" if a["status"] == "closed" else a["status"]
    print(f"  {a['source_alert_id']:20s} status={status_icon}")

print(f"\nPhase 7 Test COMPLETE")
print(f"{'=' * 70}")
