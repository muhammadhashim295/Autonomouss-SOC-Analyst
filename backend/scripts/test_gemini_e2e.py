"""Full end-to-end test with Gemini-powered generation."""
import time, requests, json

BASE = "http://localhost:8000"

print("=" * 60)
print("Phase 3b — Gemini-Powered Live Feed Test")
print("=" * 60)

# Record alert count before
r = requests.get(f"{BASE}/alerts/", params={"limit": 200})
before_alerts = r.json()
before_count = len(before_alerts)
before_ids = {a['id'] for a in before_alerts}
print(f"\nAlerts before: {before_count}")

# Start a short Gemini-powered run (15 seconds, 5 second interval, 30% poison)
print("\nStarting Gemini generation (15s, 5s interval, 30% poison)...")
r = requests.post(
    f"{BASE}/alerts/generate/start",
    params={"duration_seconds": 15, "interval_seconds": 5, "poison_ratio": 0.3},
)
start_resp = r.json()
print(f"  {r.status_code} {json.dumps(start_resp, indent=2)}")

# Wait for generation to complete (Gemini takes ~5-10s per call)
print("\nWaiting 25 seconds for generation...")
time.sleep(25)

# Check final status
r = requests.get(f"{BASE}/alerts/generate/status")
status = r.json()
print(f"\nFinal status: {json.dumps(status, indent=2)}")

# Check new alerts
r = requests.get(f"{BASE}/alerts/", params={"limit": 200})
all_alerts = r.json()
live_alerts = [a for a in all_alerts if a["source_alert_id"].startswith("LIVE-")]
new_alerts = [a for a in all_alerts if a["id"] not in before_ids]

print(f"\nAlerts after: {len(all_alerts)}")
print(f"Total LIVE alerts: {len(live_alerts)}")
print(f"\nNew alerts from this run:")
for a in live_alerts[-5:]:
    payload = a["raw_payload"]
    desc = payload.get("description", "N/A")[:70]
    print(f"  {a['source_alert_id']} | {a['alert_type']:35s} | {desc}")

# Check firewall flags
r = requests.get(f"{BASE}/alerts/firewall-flags", params={"limit": 200})
flags = r.json()
print(f"\nTotal firewall flags: {len(flags)}")

# Verify GUIDE alerts untouched
guide = [a for a in all_alerts if a["source_alert_id"].startswith("GUIDE-")]
print(f"GUIDE alerts still intact: {len(guide)}")

print("\n" + "=" * 60)
print("Phase 3b Gemini-Powered Test COMPLETE")
print("=" * 60)
