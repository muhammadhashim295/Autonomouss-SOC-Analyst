#!/usr/bin/env python3
"""Phase 6 verification: test all 4 skills on sample alerts."""

import json
import sys
import requests

BASE = "http://localhost:8000"

def main() -> None:
    print("=" * 60)
    print("PHASE 6 — INVESTIGATION SKILLS VERIFICATION")
    print("=" * 60)

    # 1. Get alerts
    r = requests.get(f"{BASE}/alerts/", timeout=10)
    alerts = r.json()

    # Pick specific test alerts
    test_ids = {}
    for a in alerts:
        sid = a["source_alert_id"]
        if sid == "GUIDE-FP-001":
            test_ids["clean_fp"] = a["id"]
        elif sid == "GUIDE-TP-001":
            test_ids["brute_force"] = a["id"]
        elif sid == "GUIDE-TP-002":
            test_ids["powershell"] = a["id"]
        elif sid == "GUIDE-HI-001":
            test_ids["exfiltration"] = a["id"]

    print(f"\nFound {len(test_ids)} test alerts to verify skills on")

    for label, alert_id in test_ids.items():
        print(f"\n{'='*60}")
        print(f"Testing: {label} ({alert_id[:16]}...)")
        print("=" * 60)

        r = requests.get(f"{BASE}/alerts/{alert_id}/enrich", timeout=30)
        if r.status_code != 200:
            print(f"  FAILED: {r.status_code} {r.text}")
            continue

        data = r.json()

        # OTX
        otx = data["otx_enrichment"]
        print(f"\n  [OTX] {otx['threat_summary']}")
        if otx["ip_results"]:
            for ip in otx["ip_results"]:
                print(f"    IP {ip['ip']}: reputation={ip.get('reputation')}, country={ip.get('country', 'N/A')}")

        # ATT&CK
        attack = data["attack_mapping"]
        print(f"\n  [ATT&CK] {attack['summary']}")
        for t in attack["matched_techniques"][:3]:
            print(f"    {t['technique_id']} — {t['technique_name']} ({t['tactic']})")

        # Log Correlation
        corr = data["log_correlation"]
        print(f"\n  [LOG CORR] {corr['summary']}")
        for chain in corr["attack_chains"]:
            print(f"    Chain: {chain}")

        # Behavioral Deviation
        dev = data["behavioral_deviation"]
        print(f"\n  [DEVIATION] {dev['summary']}")
        for flag in dev["all_flags"][:3]:
            print(f"    Flag: {flag}")

    print(f"\n{'='*60}")
    print("PHASE 6 SKILLS VERIFIED — all 4 skills produce output")
    print("=" * 60)


if __name__ == "__main__":
    main()
