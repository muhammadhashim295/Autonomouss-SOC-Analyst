"""Probe Qoder Cloud Agents API for memory/knowledge/vault endpoints."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.core.config import settings

headers = {
    "Authorization": f"Bearer {settings.qoder_pat}",
    "Content-Type": "application/json",
}
base = settings.qoder_api_base
primary = settings.qoder_primary_agent_id

# Candidate paths for memory-like features
PROBES = [
    ("GET", "/memories", None),
    ("GET", "/memory", None),
    ("GET", "/knowledge", None),
    ("GET", "/vaults", None),
    ("GET", f"/agents/{primary}/memories", None),
    ("GET", f"/agents/{primary}/memory", None),
    ("GET", "/workspaces", None),
]

for method, path, body in PROBES:
    url = f"{base}{path}"
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=10)
        else:
            r = requests.post(url, headers=headers, json=body, timeout=10)
        status = r.status_code
        body_preview = r.text[:120].replace("\n", " ")
        print(f"{method:4} {path:45} -> {status}  {body_preview if status != 404 else ''}")
    except requests.RequestException as exc:
        print(f"{method:4} {path:45} -> ERROR {exc}")

# Also try the OpenAPI spec if exposed
for spec_path in ["/openapi.json", "/../openapi.json", "/docs"]:
    try:
        r = requests.get(f"https://api.qoder.com{spec_path}", headers=headers, timeout=10)
        print(f"GET  {spec_path:45} -> {r.status_code}")
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            paths = list(r.json().get("paths", {}).keys())
            mem_paths = [p for p in paths if "mem" in p.lower() or "know" in p.lower() or "vault" in p.lower()]
            print(f"     total paths: {len(paths)}; memory-like: {mem_paths}")
    except requests.RequestException as exc:
        print(f"GET  {spec_path:45} -> ERROR {exc}")
