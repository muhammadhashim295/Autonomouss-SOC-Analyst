#!/usr/bin/env python3
"""Final test: triage a real alert."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from app.core.config import settings

headers = {
    "Authorization": f"Bearer {settings.qoder_pat}",
    "Content-Type": "application/json",
}

# Test alert
test_alert = {
    "source_alert_id": "TEST-001",
    "alert_type": "brute_force_login",
    "raw_payload": {
        "source_ip": "192.168.1.100",
        "destination_ip": "10.0.0.5",
        "destination_port": 22,
        "protocol": "TCP",
        "failed_attempts": 47,
        "time_window_minutes": 5,
        "description": "Multiple failed SSH login attempts from single source"
    }
}

# 1. Create session
print("[1] Creating session...")
resp = requests.post(
    f"{settings.qoder_api_base}/sessions",
    headers=headers,
    json={
        "agent": settings.qoder_primary_agent_id,
        "environment_id": settings.qoder_primary_env_id,
    },
    timeout=15,
)
session_id = resp.json()["id"]
print(f"    Session: {session_id}")

# 2. Send investigation prompt
prompt = f"""Investigate the following security alert and produce a full investigation report:

**Alert ID:** {test_alert['source_alert_id']}
**Alert Type:** {test_alert['alert_type']}
**Raw Payload:**
```json
{json.dumps(test_alert['raw_payload'], indent=2)}
```"""

print("\n[2] Sending investigation prompt...")
resp = requests.post(
    f"{settings.qoder_api_base}/sessions/{session_id}/events",
    headers=headers,
    json={"events": [{"type": "user.message", "content": [{"type": "text", "text": prompt}]}]},
    timeout=15,
)
print(f"    Status: {resp.status_code}")

# 3. Stream response
print("\n[3] Streaming agent response (up to 60s)...")
resp = requests.get(
    f"{settings.qoder_api_base}/sessions/{session_id}/events/stream",
    headers={"Authorization": f"Bearer {settings.qoder_pat}", "Accept": "text/event-stream"},
    stream=True,
    timeout=60,
)

collected = []
current_event = None
for line in resp.iter_lines(decode_unicode=True):
    if not line or line.startswith(": heartbeat"):
        continue
    if line.startswith("event:"):
        current_event = line[6:].strip()
        continue
    if not line.startswith("data:"):
        continue
    
    data_str = line[5:].strip()
    try:
        event = json.loads(data_str)
        if current_event == "agent.message":
            for b in event.get("content", []):
                if b.get("type") == "text":
                    collected.append(b["text"])
        if current_event and "status_idle" in current_event:
            break
    except json.JSONDecodeError:
        pass

response_text = "".join(collected)
print(f"\n{'='*60}")
print("AGENT RESPONSE:")
print("="*60)
print(response_text if response_text else "(empty)")
print("="*60)

if response_text:
    print("\nPHASE 5 VERIFIED: Agent produced reasoning!")
else:
    print("\nFAILED: No response collected")
    sys.exit(1)
