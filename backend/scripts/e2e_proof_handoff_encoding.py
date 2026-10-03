"""End-to-end proof for the two live bugs reported on the dashboard.

Bug 1 — Primary → Secondary handoff: asserts that the Secondary Deep
        Investigation Agent actually STARTS and COMPLETES, and that the run
        reaches a terminal state (closed / autonomous action / escalated),
        instead of stalling on "Investigation ongoing" forever.

Bug 2 — Mojibake: reconstructs the full reasoning text exactly as the UI does
        (from the streamed ``agent_delta`` events) and scans it for the classic
        UTF-8-decoded-as-Latin-1 signatures ("â€¢", "â€‘", "â€™", ...), then
        prints the real non-ASCII characters that came through (bullets, dashes,
        smart quotes) to prove the pipeline now stays UTF-8 end to end.

It runs the real pipeline in-process against live Groq — the same generator the
SSE route relays — and prints the complete event timeline as proof.

Usage:
    python scripts/e2e_proof_handoff_encoding.py [--keep]
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Windows consoles default to cp1252 and cannot print the arrows/dashes we emit
# in the report; force UTF-8 so the proof output itself never mangles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from app.db.supabase_client import get_supabase  # noqa: E402
from app.services.investigation_stream import run_dual_agent_stream  # noqa: E402

# Signatures produced when UTF-8 bytes are decoded as Latin-1/cp1252.
_MOJIBAKE_MARKERS = ("â€", "Ã", "Â", "€‚", "ï¿½", "Å", "Â°")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def seed_alert(supabase) -> dict:
    """Insert a clean, non-poisoned true-positive alert (brute-force SSH)."""
    source_id = f"E2E-TP-{uuid.uuid4().hex[:8].upper()}"
    row = {
        "source_alert_id": source_id,
        "alert_type": "brute_force_login",
        "status": "pending",
        "raw_payload": {
            "source_ip": "203.0.113.45",
            "destination_ip": "10.0.3.10",
            "destination_port": 22,
            "protocol": "TCP",
            "target_service": "SSH",
            "failed_attempts": 847,
            "time_window_seconds": 300,
            "unique_usernames_tried": 23,
            "usernames_sample": ["root", "admin", "ubuntu", "deploy"],
            "geo_ip": {"country": "CN", "city": "Shenzhen", "asn": "AS4134"},
            "description": "High-volume SSH brute force \u2014 dictionary attack pattern",
            "log_entries": [
                {"timestamp": "2026-08-25T08:32:10Z", "event": "Failed password for root",
                 "src": "203.0.113.45", "dst": "10.0.3.10"},
                {"timestamp": "2026-08-25T08:37:10Z", "event": "847 failed attempts in 5 minutes",
                 "src": "203.0.113.45", "dst": "10.0.3.10"},
            ],
            "iocs": ["203.0.113.45"],
            "network_zone": "external",
        },
    }
    res = supabase.table("alerts").insert(row).execute()
    if not res.data:
        raise RuntimeError("Could not seed test alert")
    return res.data[0]


def main() -> int:
    keep = "--keep" in sys.argv
    supabase = get_supabase()

    print("=" * 78)
    print(" END-TO-END PROOF — dual-agent handoff (Bug 1) + UTF-8 reasoning (Bug 2)")
    print("=" * 78)

    alert = seed_alert(supabase)
    alert_id = alert["id"]
    print(f"[{_ts()}] seeded alert {alert_id} source={alert['source_alert_id']}\n")

    started = time.time()
    timeline: list[str] = []
    reasoning: dict[str, list[str]] = {"primary": [], "secondary": []}
    milestones = {
        "primary_started": False,
        "primary_complete": False,
        "secondary_started": False,
        "secondary_complete": False,
        "investigation_complete": False,
    }
    primary_verdict = secondary_verdict = final = None
    action_status = None
    n = 0

    for ev in run_dual_agent_stream(alert):
        n += 1
        name = ev.get("event", "?")
        data = ev.get("data", {}) or {}
        agent = data.get("agent")
        elapsed = time.time() - started

        # Reconstruct the reasoning EXACTLY as the frontend does (concat deltas).
        if name == "agent_delta" and agent in reasoning:
            reasoning[agent].append(data.get("text", ""))
            continue  # don't spam the timeline with every token

        if name == "agent_started":
            milestones[f"{agent}_started"] = True
        elif name == "agent_complete":
            milestones[f"{agent}_complete"] = True
            if agent == "primary":
                primary_verdict = data.get("verdict")
            else:
                secondary_verdict = data.get("secondary_verdict") or data.get("verdict")
        elif name == "investigation_complete":
            milestones["investigation_complete"] = True
            final = data
            action_status = data.get("action_status")
        elif name == "investigation_error":
            final = {"error": data.get("detail")}

        note = ""
        if name == "agent_complete" and agent == "primary":
            note = f"  verdict={data.get('verdict')} conf={data.get('confidence')}"
        elif name == "agent_complete" and agent == "secondary":
            note = f"  sec_verdict={data.get('secondary_verdict') or data.get('verdict')}"
        elif name == "investigation_complete":
            note = f"  status={data.get('alert_status')} action={data.get('action_status')}"
        elif name == "investigation_error":
            note = f"  detail={data.get('detail')}"

        line = f"[{_ts()}] t+{elapsed:6.2f}s  #{n:<3} {name}{note}"
        timeline.append(line)
        print(line, flush=True)

    print(f"\n[{_ts()}] stream finished after {n} events, {time.time() - started:.2f}s\n")

    # ── Bug 1 assertions: the handoff actually happened & reached a terminal ──
    ok_b1 = (
        milestones["primary_started"]
        and milestones["primary_complete"]
        and milestones["secondary_started"]
        and milestones["secondary_complete"]
        and milestones["investigation_complete"]
    )

    print("-" * 78)
    print(" BUG 1 — Primary → Secondary handoff")
    print("-" * 78)
    for key, val in milestones.items():
        print(f"   {'PASS' if val else 'FAIL'}  {key}")
    print(f"   Primary verdict:   {primary_verdict}")
    print(f"   Secondary verdict: {secondary_verdict}")
    print(f"   Final action_status: {action_status}")
    print(f"   {'=> HANDOFF OK: full pipeline reached a terminal state' if ok_b1 else '=> HANDOFF INCOMPLETE'}")

    # ── Bug 2 assertions: reconstruct reasoning, scan for mojibake ──
    full_primary = "".join(reasoning["primary"])
    full_secondary = "".join(reasoning["secondary"])
    combined = full_primary + "\n" + full_secondary

    mojibake_hits = [m for m in _MOJIBAKE_MARKERS if m in combined]
    non_ascii = sorted({ch for ch in combined if ord(ch) > 127})

    print("\n" + "-" * 78)
    print(" BUG 2 — UTF-8 reasoning integrity")
    print("-" * 78)
    print(f"   Primary reasoning length:   {len(full_primary)} chars")
    print(f"   Secondary reasoning length: {len(full_secondary)} chars")
    print(f"   Mojibake signatures found:  {mojibake_hits if mojibake_hits else 'NONE (clean)'}")
    if non_ascii:
        print(f"   Real non-ASCII chars rendered correctly: "
              + ", ".join(f"{ch!r}=U+{ord(ch):04X}" for ch in non_ascii[:12]))
    else:
        print("   (this run's text happened to be pure-ASCII; mojibake scan still clean)")

    # A reasoning body that ends abruptly mid-word is the other Bug-1 symptom.
    trunc = " (TRUNCATED)" if full_primary.strip() and not full_primary.rstrip()[-1:] in {".", "”", "\"", "'", ")", "*", ":"} else ""
    print(f"   Primary reasoning tail: ...{full_primary[-90:]!r}{trunc}")

    ok_b2 = not mojibake_hits

    # ── cleanup ──
    if not keep:
        try:
            supabase.table("cases").delete().eq("alert_id", alert_id).execute()
            supabase.table("alerts").delete().eq("id", alert_id).execute()
            print(f"\n[{_ts()}] cleaned up test alert {alert_id} (use --keep to retain)")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{_ts()}] cleanup warning: {exc}")

    print("\n" + "=" * 78)
    print(f" RESULT: Bug1(handoff)={'PASS' if ok_b1 else 'FAIL'}   "
          f"Bug2(encoding)={'PASS' if ok_b2 else 'FAIL'}")
    print("=" * 78)
    return 0 if (ok_b1 and ok_b2) else 1


if __name__ == "__main__":
    sys.exit(main())
