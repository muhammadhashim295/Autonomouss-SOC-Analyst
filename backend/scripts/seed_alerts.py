#!/usr/bin/env python3
"""Seed sample alerts into the system via the POST /alerts endpoint.

Usage (run from the backend/ directory with the venv active):

    # Send all 6 sample alerts at once
    python scripts/seed_alerts.py

    # Send a specific alert by source_alert_id
    python scripts/seed_alerts.py --id GUIDE-TP-001

    # Timed replay — send all alerts with a 3-second delay between each
    python scripts/seed_alerts.py --timed --delay 3

    # Point at a different backend URL
    python scripts/seed_alerts.py --base-url http://localhost:9000
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

SAMPLES_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "sample_alerts.json"
DEFAULT_BASE_URL = "http://localhost:8000"


def load_samples() -> list[dict]:
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def send_alert(base_url: str, alert: dict) -> dict | None:
    """POST a single alert and return the response data, or None on failure."""
    url = f"{base_url}/alerts/"
    try:
        resp = requests.post(url, json=alert, timeout=10)
        if resp.status_code == 201:
            data = resp.json()
            print(f"  [OK] {alert['source_alert_id']:20s} -> id={data['id']}  status={data['status']}")
            return data
        else:
            print(f"  [FAIL] {alert['source_alert_id']:20s} -> HTTP {resp.status_code}: {resp.text}")
            return None
    except requests.ConnectionError:
        print(f"  [ERROR] Could not connect to {base_url} — is the server running?")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed sample GUIDE-like alerts into the SOC system")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL (default: %(default)s)")
    parser.add_argument("--id", default=None, help="Send only the alert with this source_alert_id")
    parser.add_argument("--timed", action="store_true", help="Send alerts sequentially with a delay")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between alerts when --timed (default: 2)")
    args = parser.parse_args()

    samples = load_samples()
    print(f"Loaded {len(samples)} sample alerts from {SAMPLES_PATH.name}\n")

    if args.id:
        match = [s for s in samples if s["source_alert_id"] == args.id]
        if not match:
            available = ", ".join(s["source_alert_id"] for s in samples)
            print(f"Alert '{args.id}' not found. Available: {available}")
            sys.exit(1)
        send_alert(args.base_url, match[0])
        return

    # Send all alerts
    print(f"Sending {len(samples)} alerts to {args.base_url}/alerts/ ...\n")
    success = 0
    for i, alert in enumerate(samples, 1):
        print(f"  [{i}/{len(samples)}]", end="")
        result = send_alert(args.base_url, alert)
        if result:
            success += 1
        if args.timed and i < len(samples):
            time.sleep(args.delay)

    print(f"\nDone: {success}/{len(samples)} alerts ingested successfully.")


if __name__ == "__main__":
    main()
