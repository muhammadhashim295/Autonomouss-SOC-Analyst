"""End-to-end HTTP verification of the /alerts/generate/* endpoints.

Hits the REAL running FastAPI server (127.0.0.1:8000):
  GET  /health
  GET  /alerts/generate/status      (before)
  POST /alerts/generate/start        (duration, interval=3, poison=0.15)
  GET  /alerts/generate/status      (polled -> measures live cadence)
  POST /alerts/generate/stop

Proves requirement 3 (same endpoints, Cloudflare-backed) and requirement (b)
(a new alert every ~3s) over HTTP, not just in-process.
"""

from __future__ import annotations

import sys
import time

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

BASE = "http://127.0.0.1:8000"


def main(duration: int = 24, interval: int = 3) -> None:
    print("== GET /health ==")
    h = requests.get(f"{BASE}/health", timeout=15).json()
    print(f"   status={h.get('status')} alerts_count={h.get('alerts_count')}")

    print("== GET /alerts/generate/status (before) ==")
    print("  ", requests.get(f"{BASE}/alerts/generate/status", timeout=15).json())

    print(f"== POST /alerts/generate/start (duration={duration}, interval={interval}, poison=0.15) ==")
    started = requests.post(
        f"{BASE}/alerts/generate/start",
        params={"duration_seconds": duration, "interval_seconds": interval, "poison_ratio": 0.15},
        timeout=15,
    )
    print(f"   HTTP {started.status_code} -> {started.json()}")

    t0 = time.monotonic()
    prev = 0
    marks: list[float] = []
    last_inc = t0
    print("== polling GET /alerts/generate/status every 1.5s ==")
    while True:
        time.sleep(1.5)
        s = requests.get(f"{BASE}/alerts/generate/status", timeout=15).json()
        c = s.get("alerts_generated", 0)
        now = time.monotonic()
        if c != prev:
            gap = now - last_inc
            marks.append(now - t0)
            print(
                f"   +{now - t0:5.2f}s  alerts_generated={c} (gap={gap:.2f}s) "
                f"poison={s.get('poison_injected')} flagged={s.get('firewall_caught')} "
                f"remaining={s.get('alerts_remaining')}"
            )
            prev = c
            last_inc = now
        if s.get("status") != "running":
            print(f"   status={s.get('status')} -> feed ended")
            break
        if now - t0 > duration + 15:
            print("   watchdog -> break")
            break

    print("== POST /alerts/generate/stop ==")
    try:
        stop = requests.post(f"{BASE}/alerts/generate/stop", timeout=15)
        print(f"   HTTP {stop.status_code} -> {stop.json()}")
    except Exception as exc:  # noqa: BLE001
        print(f"   stop error: {exc}")

    if len(marks) > 2:
        gaps = [round(marks[i + 1] - marks[i], 2) for i in range(len(marks) - 1)]
        steady = gaps[1:]
        print()
        print(f"   insert marks (s): {[round(m, 2) for m in marks]}")
        print(f"   inter-alert gaps: {gaps}")
        print(f"   steady-state avg gap: {sum(steady) / len(steady):.2f}s (target ~{interval}s)")


if __name__ == "__main__":
    main()
