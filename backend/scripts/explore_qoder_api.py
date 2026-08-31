"""Explore Qoder Cloud Agents API — list agents and environments."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.core.config import settings

headers = {
    "Authorization": f"Bearer {settings.qoder_pat}",
    "Content-Type": "application/json",
}
base = settings.qoder_api_base

# Try listing agents
for endpoint in ["/agents", "/environments", "/me", "/workspaces"]:
    try:
        resp = requests.get(f"{base}{endpoint}", headers=headers, timeout=15)
        print(f"GET {endpoint}: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"  {json.dumps(data, indent=2)[:800]}")
            except Exception:
                print(f"  {resp.text[:500]}")
        else:
            print(f"  {resp.text[:200]}")
    except Exception as e:
        print(f"GET {endpoint}: ERROR {type(e).__name__}: {e}")
    print()
