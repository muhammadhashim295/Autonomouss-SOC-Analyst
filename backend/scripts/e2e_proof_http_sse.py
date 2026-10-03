"""Live HTTP/SSE proof through the real FastAPI route (the exact path the
browser uses): POST /alerts/{id}/investigate/stream.

Complements the in-process proof by additionally verifying, over the wire:
  * the SSE response is served with Content-Type: text/event-stream; charset=utf-8
  * the relayed event stream reaches a terminal state (Primary -> Secondary)
  * the reasoning text arrives as clean UTF-8 (no mojibake signatures)
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402

from app.db.supabase_client import get_supabase  # noqa: E402

BASE = os.environ.get("SOC_BASE", "http://127.0.0.1:8051")
_MOJIBAKE = ("â€", "Ã", "Â", "€‚", "ï¿½", "Å")


def main() -> int:
    supabase = get_supabase()
    source_id = f"E2E-HTTP-{uuid.uuid4().hex[:8].upper()}"
    row = supabase.table("alerts").insert({
        "source_alert_id": source_id,
        "alert_type": "brute_force_login",
        "status": "pending",
        "raw_payload": {
            "source_ip": "203.0.113.45", "destination_ip": "10.0.3.10",
            "destination_port": 22, "target_service": "SSH", "failed_attempts": 847,
            "time_window_seconds": 300, "unique_usernames_tried": 23,
            "description": "High-volume SSH brute force \u2014 dictionary attack",
            "log_entries": [{"timestamp": "2026-08-25T08:32:10Z", "event": "Failed password for root",
                             "src": "203.0.113.45", "dst": "10.0.3.10"}],
            "iocs": ["203.0.113.45"], "network_zone": "external",
        },
    }).execute()
    alert_id = row.data[0]["id"]
    print(f"seeded {alert_id} ({source_id}) — POSTing to {BASE}/alerts/{alert_id}/investigate/stream\n")

    reasoning = {"primary": [], "secondary": []}
    seen = {}
    t0 = time.time()

    with requests.post(f"{BASE}/alerts/{alert_id}/investigate/stream",
                       stream=True, timeout=120) as resp:
        # ── Header / encoding assertions (Bug 2, item 3) ──
        ctype = resp.headers.get("Content-Type", "")
        print(f"HTTP {resp.status_code}  Content-Type: {ctype}")
        header_ok = ("text/event-stream" in ctype) and ("charset=utf-8" in ctype.lower())
        print(f"   {'PASS' if header_ok else 'FAIL'}  SSE served with explicit charset=utf-8\n")

        # Mirror the browser: force UTF-8 regardless of what requests infers.
        resp.encoding = "utf-8"
        event_name = None
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = raw.strip()
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    event_name = None
                    continue
                if event_name:
                    seen[event_name] = seen.get(event_name, 0) + 1
                    ag = data.get("agent")
                    if event_name == "agent_delta" and ag in reasoning:
                        reasoning[ag].append(data.get("text", ""))
                    elif event_name in ("agent_started", "agent_complete",
                                        "investigation_complete", "investigation_error"):
                        extra = ""
                        if event_name == "agent_complete":
                            extra = f"  agent={ag} verdict={data.get('verdict')} sec={data.get('secondary_verdict')}"
                        elif event_name == "investigation_complete":
                            extra = f"  status={data.get('alert_status')} action={data.get('action_status')}"
                        elif event_name == "investigation_error":
                            extra = f"  detail={data.get('detail')}"
                        print(f"[t+{time.time()-t0:6.2f}s] {event_name}{extra}")
                event_name = None

    combined = "".join(reasoning["primary"]) + "".join(reasoning["secondary"])
    mojibake = [m for m in _MOJIBAKE if m in combined]
    non_ascii = sorted({c for c in combined if ord(c) > 127})

    print(f"\nprimary_delta_chars={len(''.join(reasoning['primary']))} "
          f"secondary_delta_chars={len(''.join(reasoning['secondary']))}")
    print(f"mojibake_signatures={mojibake or 'NONE (clean)'}")
    if non_ascii:
        print("non-ASCII decoded correctly: " + ", ".join(f"{c!r}=U+{ord(c):04X}" for c in non_ascii[:10]))

    handoff_ok = seen.get("agent_started", 0) >= 2 and "investigation_complete" in seen
    enc_ok = not mojibake

    supabase.table("cases").delete().eq("alert_id", alert_id).execute()
    supabase.table("alerts").delete().eq("id", alert_id).execute()

    print("\n" + "=" * 70)
    print(f" OVER-HTTP RESULT: handoff={'PASS' if handoff_ok else 'FAIL'}  "
          f"sse_charset={'PASS' if header_ok else 'FAIL'}  encoding={'PASS' if enc_ok else 'FAIL'}")
    print("=" * 70)
    return 0 if (handoff_ok and header_ok and enc_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
