"""Explore the Qoder vaults API — can it serve as the memory store?"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from app.core.config import settings

headers = {
    "Authorization": f"Bearer {settings.qoder_pat}",
    "Content-Type": "application/json",
}
base = settings.qoder_api_base

# 1. Try creating a vault — discover the required fields from the error
print("=== POST /vaults (minimal) ===")
r = requests.post(f"{base}/vaults", headers=headers, json={"display_name": "soc-memory-store"}, timeout=15)
print(f"status={r.status_code}")
print(f"body={r.text[:500]}\n")

# 2. If a vault was created, probe item endpoints under it
if r.status_code in (200, 201):
    vault = r.json()
    vid = vault.get("id") or vault.get("vault_id")
    print(f"vault created: {json.dumps(vault)[:300]}\n")

    item_paths = [
        f"/vaults/{vid}/items",
        f"/vaults/{vid}/documents",
        f"/vaults/{vid}/files",
        f"/vaults/{vid}/entries",
        f"/vaults/{vid}/records",
        f"/vaults/{vid}/secrets",
    ]
    for p in item_paths:
        rr = requests.get(f"{base}{p}", headers=headers, timeout=10)
        print(f"GET  {p:50} -> {rr.status_code}  {rr.text[:100]}")

    # Try posting an item
    print("\n=== POST /vaults/{id}/items (minimal) ===")
    rr = requests.post(
        f"{base}/vaults/{vid}/items",
        headers=headers,
        json={"name": "case-GUIDE-TP-001", "content": json.dumps({"verdict": "true_positive"})},
        timeout=15,
    )
    print(f"status={rr.status_code}")
    print(f"body={rr.text[:500]}")

    # Cleanup probe vault if nothing else uses it
    # (leave it — we may adopt it for the memory store)
