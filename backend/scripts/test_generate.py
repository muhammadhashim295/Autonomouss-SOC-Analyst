"""Quick test for Phase 3b — Gemini client + generator endpoints."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.gemini_client import GeminiClient

# 1. Test Gemini client (template fallback since no API key)
print("=" * 60)
print("Phase 3b Test — Gemini Client")
print("=" * 60)

gc = GeminiClient()
print(f"Gemini API available: {gc.available}")
print()

# Generate 3 alerts without poison
print("--- 3 normal alerts ---")
for i in range(3):
    alert = gc.generate_alert()
    print(f"  [{i+1}] {alert['source_alert_id']} | {alert['alert_type']}")
    print(f"      payload keys: {list(alert['raw_payload'].keys())}")
    desc = alert["raw_payload"].get("description", "N/A")[:80]
    print(f"      desc: {desc}")
print()

# Generate 3 poison alerts
print("--- 3 poison alerts ---")
for i in range(3):
    alert = gc.generate_alert(inject_poison=True)
    print(f"  [{i+1}] {alert['source_alert_id']} | {alert['alert_type']}")
    payload = alert["raw_payload"]
    # Check if poison was injected
    suspicious = False
    import json
    text = json.dumps(payload)
    for pattern in ["ignore all previous", "false_positive", "maintenance mode", "<system>", "New instructions"]:
        if pattern.lower() in text.lower():
            suspicious = True
            break
    print(f"      poison detected: {suspicious}")
print()

# 2. Test firewall catches poison
print("--- Firewall test on poison alerts ---")
from app.core.firewall import check_alert

poison_count = 0
for i in range(10):
    alert = gc.generate_alert(inject_poison=True)
    flags = check_alert(
        source_alert_id=alert["source_alert_id"],
        alert_type=alert["alert_type"],
        raw_payload=alert["raw_payload"],
    )
    if flags:
        poison_count += 1
        print(f"  FLAGGED: {alert['source_alert_id']} -> {flags[0]}")
    else:
        print(f"  CLEAN:   {alert['source_alert_id']} (poison variant not detected by firewall)")

print(f"\nFirewall caught {poison_count}/10 poison alerts")
print()

# 3. Test all 10 alert types
print("--- All alert types ---")
from app.services.gemini_client import _ALERT_TYPES
for at in _ALERT_TYPES:
    from app.services.gemini_client import _generate_from_template
    payload = _generate_from_template(at)
    print(f"  {at:40s} | keys: {len(payload)}")

print()
print("Phase 3b client test COMPLETE")
