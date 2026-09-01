"""Verify: secondary agent exists in Qoder + sessions bound to it."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.core.config import settings

headers = {
    "Authorization": f"Bearer {settings.qoder_pat}",
    "Content-Type": "application/json",
}
base = settings.qoder_api_base

# 1. List all agents — show both exist as persistent definitions
resp = requests.get(f"{base}/agents", headers=headers, timeout=15)
agents = resp.json().get("data", [])
print(f"AGENTS REGISTERED IN QODER ({len(agents)}):")
for a in agents:
    tag = "PRIMARY" if a["id"] == settings.qoder_primary_agent_id else (
        "SECONDARY" if a["id"] == settings.qoder_secondary_agent_id else "?"
    )
    print(f"  [{tag}] {a['name']}")
    print(f"          id={a['id']}")
    print(f"          model={a.get('model', {}).get('id')} effort={a.get('model', {}).get('effort')}")
    print(f"          system prompt: {len(a.get('system', ''))} chars")
print()

# 2. List sessions — show a session was created bound to the secondary agent
resp = requests.get(f"{base}/sessions", headers=headers, timeout=15)
sessions = resp.json().get("data", [])
print(f"RECENT SESSIONS ({len(sessions)}):")
for s in sessions[:10]:
    agent_ref = s.get("agent", s.get("agent_id", "?"))
    tag = "SECONDARY" if agent_ref == settings.qoder_secondary_agent_id else (
        "PRIMARY" if agent_ref == settings.qoder_primary_agent_id else str(agent_ref)[:20]
    )
    print(f"  [{tag}] session={s.get('id')} created={s.get('created_at', '?')[:19]}")
