"""Diagnostic: run the dual-agent SSE pipeline in-process and surface the real
exception behind the HTTP 500 seen on POST /alerts/{id}/investigate/stream."""
from __future__ import annotations

import asyncio
import sys
import traceback

sys.path.insert(0, ".")

from app.db.supabase_client import get_supabase
from app.services.investigation_stream import run_dual_agent_stream


async def main(alert_id: str) -> int:
    supabase = get_supabase()
    row = supabase.table("alerts").select("*").eq("id", alert_id).limit(1).execute()
    if not row.data:
        print(f"alert {alert_id} not found")
        return 1
    alert = row.data[0]
    print(f"alert={alert_id} type={alert.get('alert_type')} org={alert.get('org_id')}")
    print("-" * 70)

    events = 0
    try:
        # run_dual_agent_stream is a SYNC generator that performs blocking
        # network I/O — run it in a worker thread, exactly as the SSE route does.
        for ev in run_dual_agent_stream(alert):
            events += 1
            name = ev.get("event", "?")
            data = str(ev.get("data", ""))
            print(f"[{events:02d}] {name}: {data[:220]}", flush=True)
    except Exception:
        print("-" * 70)
        print("EXCEPTION raised inside run_dual_agent_stream:")
        traceback.print_exc()
        return 2

    print("-" * 70)
    print(f"completed with {events} events, no exception")
    return 0


if __name__ == "__main__":
    aid = sys.argv[1] if len(sys.argv) > 1 else "a4acec75-b2cf-4fbf-863d-dc24ba6a7edf"
    sys.exit(asyncio.run(main(aid)))
