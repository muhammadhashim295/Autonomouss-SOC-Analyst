"""Get full details of existing agents and environments."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.core.config import settings

headers = {
    "Authorization": f"Bearer {settings.qoder_pat}",
    "Content-Type": "application/json",
}
base = settings.qoder_api_base

# Full agent list
resp = requests.get(f"{base}/agents", headers=headers, timeout=15)
agents = resp.json()
print(f"AGENTS ({len(agents.get('data', []))}):")
for a in agents.get("data", []):
    print(f"\n  ID: {a['id']}")
    print(f"  Name: {a['name']}")
    print(f"  Model: {a.get('model', {}).get('id')} (effort: {a.get('model', {}).get('effort')})")
    print(f"  Skills: {a.get('skills')}")
    print(f"  MCP servers: {a.get('mcp_servers')}")
    print(f"  System prompt (first 300): {a.get('system', '')[:300]}")
    print(f"  ---")

# Full environment list
resp = requests.get(f"{base}/environments", headers=headers, timeout=15)
envs = resp.json()
print(f"\n\nENVIRONMENTS ({len(envs.get('data', []))}):")
for e in envs.get("data", []):
    print(f"\n  ID: {e['id']}")
    print(f"  Name: {e['name']}")
    print(f"  Config: {json.dumps(e.get('config', {}), indent=4)[:500]}")
    print(f"  ---")

# Get primary agent's FULL system prompt for reference
print("\n\n" + "=" * 70)
print("PRIMARY AGENT FULL SYSTEM PROMPT:")
print("=" * 70)
for a in agents.get("data", []):
    if a["id"] == settings.qoder_primary_agent_id:
        print(a.get("system", ""))
