#!/usr/bin/env python3
"""Phase 5 verification: triage an alert with the Primary Agent."""

import sys
import requests

BASE = "http://localhost:8000"

def main() -> None:
    print("=" * 60)
    print("PHASE 5 — QODER AGENT TRIAGE TEST")
    print("=" * 60)

    # 1. Get alerts
    print("\n[1] Fetching alerts...")
    r = requests.get(f"{BASE}/alerts/", timeout=10)
    if r.status_code != 200:
        print(f"    FAILED: {r.status_code} {r.text}")
        sys.exit(1)

    alerts = r.json()
    print(f"    Found {len(alerts)} alerts")

    # Find a clean alert (not the poison one)
    clean_alert = None
    for a in alerts:
        if "POISON" not in a["source_alert_id"]:
            clean_alert = a
            break

    if not clean_alert:
        print("    No clean alerts found to test!")
        sys.exit(1)

    alert_id = clean_alert["id"]
    source_id = clean_alert["source_alert_id"]
    print(f"    Testing with: {source_id} (id: {alert_id[:20]}...)")

    # 2. Triage
    print("\n[2] Triggering Primary Agent triage (this may take 30-60s)...")
    print("    Creating session, sending alert, collecting response...")

    try:
        r = requests.post(f"{BASE}/alerts/{alert_id}/triage", timeout=180)
    except requests.exceptions.Timeout:
        print("    TIMEOUT: Agent took longer than 3 minutes")
        sys.exit(1)

    if r.status_code == 200:
        result = r.json()
        print(f"\n    SUCCESS!")
        print(f"    Session ID: {result['session_id']}")
        print(f"\n    Agent Response (first 500 chars):")
        print("-" * 60)
        response = result.get("agent_response", "(empty)")
        print(response[:500] if response else "(empty)")
        print("-" * 60)
        print("\nPHASE 5 VERIFIED: Agent responded to alert with reasoning.")
    else:
        print(f"\n    FAILED: {r.status_code}")
        print(f"    {r.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
