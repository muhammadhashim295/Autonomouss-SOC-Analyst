"""Focused live-feed verification — Cloudflare Workers AI parse + ~3s cadence.

PHASE 1 — times individual live ``generate_alert(require_live=True)`` calls and
validates the parsed payload.  Proves the JSON parser fix works on real model
output (no "Extra data" / template substitution).

PHASE 2 — runs the real asyncio generation loop for a short bounded window and
measures the gaps between ``alerts_generated`` increments.  Proves the live feed
produces a new alert every ~3s (remainder-based sleep keeps cadence at the
interval even though each Cloudflare call consumes part of the window).

Run from the ``backend`` directory:  ``python scripts/verify_live_feed.py``
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from app.services import alert_generator
from app.services.cloudflare_client import CloudflareClient, CloudflareGenerationError


def phase1_live_calls(n: int = 3) -> list[float]:
    print("=" * 66)
    print("PHASE 1 - timed LIVE Cloudflare generate_alert(require_live=True)")
    print("=" * 66)
    cf = CloudflareClient()
    print(f"  available = {cf.available}")
    print(f"  model     = {cf._model}")
    print(f"  account   = {cf._account_id}")
    print()

    latencies: list[float] = []
    ok = 0
    for i in range(n):
        t0 = time.monotonic()
        try:
            alert = cf.generate_alert(inject_poison=(i == n - 1), require_live=True)
        except CloudflareGenerationError as exc:
            dt = time.monotonic() - t0
            print(f"  [{i + 1}] FAILED after {dt:.2f}s: {exc}")
            continue
        dt = time.monotonic() - t0
        latencies.append(dt)
        ok += 1
        payload = alert["raw_payload"]
        desc = str(payload.get("description", "N/A"))[:66]
        has_logs = isinstance(payload.get("log_entries"), list)
        n_logs = len(payload.get("log_entries", [])) if has_logs else 0
        print(f"  [{i + 1}] {dt:5.2f}s | {alert['alert_type']:30s} | keys={len(payload):2d} logs={n_logs}")
        print(f"        id   = {alert['source_alert_id']}")
        print(f"        desc = {desc}")
    print()
    if latencies:
        print(
            f"  LIVE parse OK: {ok}/{n} | latency min={min(latencies):.2f}s "
            f"avg={sum(latencies) / len(latencies):.2f}s max={max(latencies):.2f}s"
        )
    else:
        print("  No successful live calls.")
    return latencies


async def phase2_loop_cadence(duration: int = 12, interval: int = 3) -> None:
    print()
    print("=" * 66)
    print(f"PHASE 2 - real generation loop (duration={duration}s, interval={interval}s)")
    print("=" * 66)
    started = alert_generator.start_generation(
        duration_seconds=duration, interval_seconds=interval, poison_ratio=0.0
    )
    print(
        f"  start_generation -> run_id={started['run_id']} "
        f"generator={started['generator']} estimated_alerts={started['estimated_alerts']}"
    )

    t_start = time.monotonic()
    last_count = 0
    gaps: list[float] = []
    last_increment_t = t_start
    st: dict = {}
    while True:
        await asyncio.sleep(0.4)
        st = alert_generator.get_generator_status()
        now = time.monotonic()
        count = st.get("alerts_generated", 0)
        if count > last_count:
            gap = now - last_increment_t
            gaps.append(gap)
            print(f"  +{now - t_start:5.2f}s  alerts_generated={count}  (gap={gap:.2f}s)")
            last_count = count
            last_increment_t = now
        if st.get("status") != "running":
            break
        if now - t_start > duration + 10:
            print("  [watchdog] breaking poll loop")
            break

    try:
        alert_generator.stop_generation()
    except RuntimeError:
        pass

    print()
    if gaps:
        print(
            f"  inserted {last_count} alerts | inter-alert gaps: "
            + ", ".join(f"{g:.2f}s" for g in gaps)
        )
        print(f"  avg cadence = {sum(gaps) / len(gaps):.2f}s (target ~{interval}s)")
    else:
        print(f"  no alerts inserted | status={st.get('status')} last_error={st.get('last_error')}")


if __name__ == "__main__":
    phase1_live_calls(3)
    asyncio.run(phase2_loop_cadence(duration=30, interval=3))
    print()
    print("Live-feed verification COMPLETE")
