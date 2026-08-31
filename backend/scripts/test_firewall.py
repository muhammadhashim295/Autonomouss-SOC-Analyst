#!/usr/bin/env python3
"""Phase 4 verification: prove the firewall catches poisoned logs."""

import json
import sys
from pathlib import Path

import requests

BASE = "http://localhost:8000"
SAMPLES = Path(__file__).resolve().parent.parent / "app" / "data" / "sample_alerts.json"


def main() -> None:
    # 1. Clear existing data
    print("=" * 60)
    print("PHASE 4 — FIREWALL VERIFICATION")
    print("=" * 60)

    # 2. Load samples
    with open(SAMPLES, encoding="utf-8") as f:
        samples = json.load(f)

    clean = next(s for s in samples if s["source_alert_id"] == "GUIDE-FP-001")
    poison = next(s for s in samples if s["source_alert_id"] == "GUIDE-POISON-001")

    # 3. Send a clean alert
    print("\n[A] Sending CLEAN alert (GUIDE-FP-001) ...")
    r = requests.post(f"{BASE}/alerts/", json=clean, timeout=10)
    if r.status_code == 201:
        clean_id = r.json()["id"]
        print(f"    OK — id={clean_id}")
    else:
        print(f"    FAIL — HTTP {r.status_code}: {r.text}")
        sys.exit(1)

    # 4. Send the poisoned-log alert
    print("\n[B] Sending POISONED alert (GUIDE-POISON-001) ...")
    r = requests.post(f"{BASE}/alerts/", json=poison, timeout=10)
    if r.status_code == 201:
        poison_id = r.json()["id"]
        print(f"    OK — id={poison_id}")
    else:
        print(f"    FAIL — HTTP {r.status_code}: {r.text}")
        sys.exit(1)

    # 5. Check firewall flags
    print("\n[C] Checking firewall flags ...")
    r = requests.get(f"{BASE}/alerts/firewall-flags", timeout=10)
    all_flags = r.json()

    clean_flags = [f for f in all_flags if f["alert_id"] == clean_id]
    poison_flags = [f for f in all_flags if f["alert_id"] == poison_id]

    print(f"\n    Clean alert  ({clean_id[:8]}...): {len(clean_flags)} flag(s)")
    if clean_flags:
        for f in clean_flags:
            print(f"      - {f['flag_reason']}")

    print(f"\n    Poison alert ({poison_id[:8]}...): {len(poison_flags)} flag(s)")
    for f in poison_flags:
        print(f"      - {f['flag_reason']}")

    # 6. Verdict
    print("\n" + "=" * 60)
    if len(clean_flags) == 0 and len(poison_flags) > 0:
        print("PASS: clean alert passed, poison alert caught!")
    else:
        print("FAIL: unexpected result")
        if clean_flags:
            print("  - clean alert should have 0 flags")
        if not poison_flags:
            print("  - poison alert should have >0 flags")
    print("=" * 60)


if __name__ == "__main__":
    main()
