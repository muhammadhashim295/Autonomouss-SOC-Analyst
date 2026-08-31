"""Test the 3 generate endpoints end-to-end."""

import time
import requests

BASE = "http://localhost:8000"

print("=" * 60)
print("Phase 3b — API Endpoint Test")
print("=" * 60)

# 1. Check status (should be idle)
print("\n1. GET /alerts/generate/status (before start)")
r = requests.get(f"{BASE}/alerts/generate/status")
print(f"   {r.status_code} {r.json()}")

# 2. Start a short run (20 seconds, 3 second interval, 20% poison)
print("\n2. POST /alerts/generate/start (20s, 3s interval, 0.2 poison)")
r = requests.post(
    f"{BASE}/alerts/generate/start",
    params={"duration_seconds": 20, "interval_seconds": 3, "poison_ratio": 0.2},
)
print(f"   {r.status_code} {r.json()}")
run_data = r.json()

if r.status_code == 200:
    # 3. Check status (should be running)
    print("\n3. GET /alerts/generate/status (after start)")
    r = requests.get(f"{BASE}/alerts/generate/status")
    status = r.json()
    print(f"   {r.status_code} status={status['status']}, "
          f"generated={status.get('alerts_generated', 0)}, "
          f"planned={status.get('total_planned', 0)}")

    # 4. Wait 8 seconds, check progress
    print("\n4. Waiting 8 seconds...")
    time.sleep(8)

    r = requests.get(f"{BASE}/alerts/generate/status")
    status = r.json()
    print(f"   {r.status_code} status={status['status']}, "
          f"generated={status.get('alerts_generated', 0)}, "
          f"poison={status.get('poison_injected', 0)}, "
          f"firewall_caught={status.get('firewall_caught', 0)}, "
          f"remaining={status.get('alerts_remaining', 0)}")

    # 5. Stop early
    print("\n5. POST /alerts/generate/stop")
    r = requests.post(f"{BASE}/alerts/generate/stop")
    print(f"   {r.status_code} {r.json()}")

    # 6. Check status (should be idle)
    print("\n6. GET /alerts/generate/status (after stop)")
    r = requests.get(f"{BASE}/alerts/generate/status")
    print(f"   {r.status_code} {r.json()}")

    # 7. Check Supabase for LIVE-* alerts
    print("\n7. Checking Supabase for LIVE-* alerts...")
    r = requests.get(f"{BASE}/alerts/", params={"limit": 200})
    all_alerts = r.json()
    live_alerts = [a for a in all_alerts if a["source_alert_id"].startswith("LIVE-")]
    print(f"   Total alerts in DB: {len(all_alerts)}")
    print(f"   LIVE-* alerts: {len(live_alerts)}")
    for a in live_alerts[:5]:
        print(f"     {a['source_alert_id']} | {a['alert_type']} | {a['status']}")

    # 8. Check firewall flags for LIVE alerts
    print("\n8. Checking firewall flags...")
    r = requests.get(f"{BASE}/alerts/firewall-flags", params={"limit": 200})
    all_flags = r.json()
    print(f"   Total firewall flags: {len(all_flags)}")

    # 9. Try to start while already idle (should work)
    print("\n9. POST /alerts/generate/start again (should succeed)")
    r = requests.post(
        f"{BASE}/alerts/generate/start",
        params={"duration_seconds": 10, "interval_seconds": 5, "poison_ratio": 0.15},
    )
    print(f"   {r.status_code} {r.json()}")
    time.sleep(2)
    r = requests.post(f"{BASE}/alerts/generate/stop")
    print(f"   Stopped: {r.status_code} {r.json()}")

    # 10. Try to start while already running (should fail with 409)
    print("\n10. POST /alerts/generate/start x2 (second should 409)")
    r1 = requests.post(
        f"{BASE}/alerts/generate/start",
        params={"duration_seconds": 30, "interval_seconds": 3, "poison_ratio": 0.15},
    )
    print(f"   First:  {r1.status_code}")
    r2 = requests.post(
        f"{BASE}/alerts/generate/start",
        params={"duration_seconds": 30, "interval_seconds": 3, "poison_ratio": 0.15},
    )
    print(f"   Second: {r2.status_code} {r2.json()}")
    # Clean up
    requests.post(f"{BASE}/alerts/generate/stop")

print("\n" + "=" * 60)
print("Phase 3b API test COMPLETE")
print("=" * 60)
