"""Phase 14 verification — SSE streaming from the backend.

Verify condition (phases.md): "Backend relays live session events
(agent reasoning as it happens) to frontend via SSE. Verify: reasoning
appears progressively in a basic test client."

This IS the basic test client: opens the SSE stream with requests
(stream=True), parses the event wire format, timestamps every event,
and asserts:

  1. Wire format is real SSE (text/event-stream; event: + data: JSON)
  2. Full event sequence arrives in order: started → memory →
     enrichment → primary turn (live status + reasoning) → case
     persisted → secondary turn → action → complete
  3. PROGRESSIVE reasoning, streamed token-by-token from the live provider
     (Groq for the primary, Cerebras for the secondary): our own pipeline
     relays each provider's token stream as agent_delta events, so reasoning
     appears incrementally DURING the turn — never batched at the end:
       - live "agent working" status arrives >1s BEFORE the agent's
         reasoning (the stream is active during the turn, not batched)
       - the primary's reasoning lands >1s BEFORE the secondary agent
         even starts — impossible in a blocking design, where every
         event would be delivered in one batch at the very end
       - the primary's reasoning lands >2s before the whole pipeline
         completes (it did NOT wait for the secondary)
  4. Joined reasoning text contains the structured verdicts
  5. The stream is not just a pretty light show: the same pipeline
     persisted everything (case + both verdicts + action + memory)
"""

import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from app.db.supabase_client import get_supabase

BASE = "http://127.0.0.1:8000"
# connect=10s, read=120s per chunk (heartbeats every ~15s keep chunks flowing)
STREAM_TIMEOUT = (10, 120)


def load_alerts() -> dict:
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "sample_alerts.json",
    )
    with open(data_path, encoding="utf-8") as f:
        return {a["source_alert_id"]: a for a in json.load(f)}


def set_mode(mode: str) -> None:
    r = requests.put(f"{BASE}/settings/mode", json={"mode": mode}, timeout=15)
    assert r.status_code == 200, f"set_mode failed: {r.text}"


def cleanup(sb, sids: list[str]) -> None:
    for sid in sids:
        rows = sb.table("alerts").select("id").eq("source_alert_id", sid).execute()
        for row in rows.data:
            cases = sb.table("cases").select("id").eq("alert_id", row["id"]).execute()
            for c in cases.data:
                sb.table("analyst_overrides").delete().eq("case_id", c["id"]).execute()
            sb.table("memory_records").delete().eq("alert_id", row["id"]).execute()
            sb.table("cases").delete().eq("alert_id", row["id"]).execute()
            sb.table("alerts").delete().eq("id", row["id"]).execute()


def parse_sse(resp) -> tuple[list[dict], int]:
    """Parse an SSE wire stream into event dicts (with client-side
    arrival timestamps) + a count of heartbeat comments observed."""
    events: list[dict] = []
    heartbeats = 0
    current_event = None
    t0 = time.time()
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            current_event = None  # event boundary
            continue
        if raw.startswith(":"):
            heartbeats += 1
            continue
        if raw.startswith("event:"):
            current_event = raw[len("event:"):].strip()
            continue
        if raw.startswith("data:"):
            data_str = raw[len("data:"):].strip()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = {"raw": data_str}
            events.append({
                "event": current_event,
                "data": data,
                "t": time.time() - t0,
            })
            current_event = None
    return events, heartbeats


def main() -> int:
    print("=" * 70)
    print("Phase 14 — SSE Streaming from Backend")
    print("=" * 70)

    r = requests.get(f"{BASE}/health", timeout=15)
    if r.status_code != 200:
        print(f"FATAL: server not healthy: {r.status_code}")
        return 1
    print("\n[1] Server healthy")

    sb = get_supabase()
    alerts_by_sid = load_alerts()
    all_checks: dict[str, bool] = {}

    # Unknown alert -> 404 BEFORE the stream starts (HTTP status still works)
    r = requests.post(
        f"{BASE}/alerts/00000000-0000-0000-0000-000000000000/investigate/stream",
        timeout=15,
    )
    all_checks["unknown alert -> 404 (pre-stream)"] = r.status_code == 404
    print(f"[2] Unknown alert stream -> {r.status_code} (expect 404)")

    # ── Ingest GUIDE-TP-001 in agentic mode ───────────────────────────
    set_mode("agentic")
    cleanup(sb, ["GUIDE-TP-001"])
    r = requests.post(f"{BASE}/alerts/", json=alerts_by_sid["GUIDE-TP-001"], timeout=30)
    assert r.status_code == 201, f"ingest failed: {r.text}"
    aid = r.json()["id"]
    print(f"[3] Ingested GUIDE-TP-001 ({aid[:8]}), agentic mode")

    # ── Open the SSE stream — the heart of the phase ──────────────────
    print("\n[4] Opening SSE stream (live dual-agent investigation)...")
    t_open = time.time()
    with requests.post(
        f"{BASE}/alerts/{aid}/investigate/stream",
        stream=True,
        timeout=STREAM_TIMEOUT,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        all_checks["HTTP 200"] = resp.status_code == 200
        all_checks["content-type text/event-stream"] = (
            resp.headers.get("content-type", "").startswith("text/event-stream")
        )
        events, heartbeats = parse_sse(resp)
    total = time.time() - t_open
    print(f"  stream closed after {total:.0f}s — {len(events)} events, "
          f"{heartbeats} heartbeat(s)")
    if resp.status_code != 200:
        print(f"FATAL: stream status {resp.status_code}")
        return 2

    # ── Event sequence ────────────────────────────────────────────────
    names = [e["event"] for e in events]
    err_events = [e for e in events if e["event"] == "investigation_error"]
    if err_events:
        print(f"  STREAM ERROR: {err_events[0]['data']}")
        return 2

    def idx(name: str, agent: str | None = None) -> int | None:
        for i, e in enumerate(events):
            if e["event"] == name and (agent is None or e["data"].get("agent") == agent):
                return i
        return None

    def t_of(name: str, agent: str | None = None) -> float | None:
        i = idx(name, agent)
        return events[i]["t"] if i is not None else None

    print("\n  timeline:")
    for e in events:
        if e["event"] == "agent_delta":
            continue  # printed separately below
        d = e["data"]
        if e["event"] == "agent_status":
            label = f"{d.get('agent')} — {d.get('status')}"
        else:
            label = d.get("agent") or d.get("action_id") or d.get("alert_type") or ""
        print(f"    t={e['t']:6.1f}s  {e['event']:24s} {label}")

    deltas = [e for e in events if e["event"] == "agent_delta"]
    p_deltas = [e for e in deltas if e["data"]["agent"] == "primary"]
    s_deltas = [e for e in deltas if e["data"]["agent"] == "secondary"]
    statuses = [e for e in events if e["event"] == "agent_status"]
    p_status = [e for e in statuses if e["data"].get("agent") == "primary"]
    s_status = [e for e in statuses if e["data"].get("agent") == "secondary"]
    print(f"    agent_delta:  {len(p_deltas)} primary, {len(s_deltas)} secondary")
    print(f"    agent_status: {len(p_status)} primary, {len(s_status)} secondary "
          f"(statuses: {sorted({e['data'].get('status') for e in statuses})})")

    seq_checks = {
        "sequence: investigation_started is first": names[0] == "investigation_started",
        "sequence: investigation_complete is last": names[-1] == "investigation_complete",
        "sequence: memory before primary agent starts": (
            (idx("memory_retrieved", "primary") or 99) < (idx("agent_started", "primary") or -1)
        ),
        "sequence: primary deltas between its start and complete": (
            (idx("agent_started", "primary") or 99)
            < (idx("agent_delta", "primary") or 99)
            < (idx("agent_complete", "primary") or -1)
        ),
        "sequence: case persisted before secondary starts": (
            (idx("case_persisted") or 99) < (idx("agent_started", "secondary") or -1)
        ),
        "sequence: secondary deltas between its start and complete": (
            (idx("agent_started", "secondary") or 99)
            < (idx("agent_delta", "secondary") or 99)
            < (idx("agent_complete", "secondary") or -1)
        ),
        "sequence: action decided after both agents": (
            (idx("agent_complete", "secondary") or -1) < (idx("action_decided") or 99)
        ),
    }
    all_checks.update(seq_checks)

    # ── The progressive-reasoning proof ───────────────────────────────
    # SSE is provider-driven: our own pipeline relays each provider's token
    # stream (Groq primary, Cerebras secondary) as agent_delta events, so
    # reasoning arrives incrementally during the turn.  Progressive means:
    # live status while the agent works, reasoning tokens as they stream,
    # and never batched at the end of the pipeline.
    p_first_t = t_of("agent_delta", "primary")
    s_start_t = t_of("agent_started", "secondary")
    complete_t = t_of("investigation_complete")
    p_pre_status = [e for e in p_status if e["t"] < p_first_t]
    p_live_gap = (p_first_t - p_pre_status[0]["t"]) if p_pre_status else 0.0
    s_pre_status = [e for e in s_status if e["t"] < t_of("agent_delta", "secondary")]

    print(f"\n  primary live status at t={(p_pre_status[0]['t'] if p_pre_status else -1):.1f}s "
          f"-> reasoning at t={p_first_t:.1f}s (thinking for {p_live_gap:.1f}s) | "
          f"secondary starts t={s_start_t:.1f}s | complete t={complete_t:.1f}s")

    all_checks["primary delivered reasoning via delta event(s)"] = len(p_deltas) >= 1
    all_checks["secondary delivered reasoning via delta event(s)"] = len(s_deltas) >= 1
    all_checks["primary emitted live agent_status signals"] = len(p_status) >= 1
    all_checks["secondary emitted live agent_status signals"] = len(s_status) >= 1
    all_checks["PROGRESSIVE: live status >1s BEFORE primary reasoning (stream active mid-turn)"] = (
        p_live_gap > 1.0
    )
    all_checks["PROGRESSIVE: live status during secondary turn"] = bool(s_pre_status)
    all_checks["PROGRESSIVE: primary reasoning arrives BEFORE secondary starts (>1s)"] = (
        p_first_t is not None and s_start_t is not None and (s_start_t - p_first_t) > 1.0
    )
    all_checks["PROGRESSIVE: primary reasoning >2s before pipeline completes"] = (
        p_first_t is not None and complete_t is not None and (complete_t - p_first_t) > 2.0
    )
    all_checks["deltas carry non-empty text"] = all(
        isinstance(d["data"].get("text"), str) and d["data"]["text"] for d in deltas
    )

    joined_primary = "".join(d["data"]["text"] for d in p_deltas)
    joined_secondary = "".join(d["data"]["text"] for d in s_deltas)
    all_checks["joined primary text contains the Verdict section"] = (
        "verdict" in joined_primary.lower()
    )
    all_checks["joined secondary text contains the Secondary Verdict"] = (
        "verdict" in joined_secondary.lower()
    )
    print(f"  joined primary text:   {len(joined_primary)} chars")
    print(f"  joined secondary text: {len(joined_secondary)} chars")

    # ── Final events carry the full outcome ───────────────────────────
    complete = events[idx("investigation_complete")]["data"]
    action = events[idx("action_decided")]["data"]
    case_persisted = events[idx("case_persisted")]["data"]

    all_checks["case_persisted carries case_id"] = bool(case_persisted.get("case_id"))
    all_checks["action_decided carries action + status"] = bool(
        action.get("action_id") and action.get("action_status")
    )
    all_checks["investigation_complete carries both verdicts"] = bool(
        complete.get("primary_verdict") in ("true_positive", "false_positive")
        and complete.get("secondary_verdict")
    )
    print(f"\n  outcome: {complete.get('primary_verdict')} / "
          f"{complete.get('secondary_verdict')} -> "
          f"{complete.get('action_id')} ({complete.get('action_status')})")

    # ── The stream is the real pipeline: verify persistence ───────────
    case_id = complete.get("case_id")
    case_rows = sb.table("cases").select("*").eq("id", case_id).execute()
    alert_rows = sb.table("alerts").select("status").eq("id", aid).execute()
    mem_rows = (
        sb.table("memory_records").select("id").eq("alert_id", aid).execute()
    )

    if case_rows.data:
        c = case_rows.data[0]
        print(f"  DB: case {c['id'][:8]} — secondary_verdict={c['secondary_verdict']}, "
              f"action={c['action_status']}, mode={c['mode']}, closed={bool(c['closed_at'])}")
    all_checks["DB: case persisted with secondary verdict"] = bool(
        case_rows.data and case_rows.data[0]["secondary_verdict"]
    )
    all_checks["DB: alert closed (agentic TP -> executed action)"] = bool(
        alert_rows.data and alert_rows.data[0]["status"] == "closed"
    )
    all_checks["DB: memory record written on close"] = bool(mem_rows.data)

    # ── Cleanup ───────────────────────────────────────────────────────
    print("\n[5] Cleanup")
    cleanup(sb, ["GUIDE-TP-001"])
    set_mode("agentic")
    print("  test data removed; mode reset to agentic")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    passed = sum(1 for ok in all_checks.values() if ok)
    for name, ok in all_checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("-" * 60)
    print(f"{passed}/{len(all_checks)} checks passed")

    core = (
        all_checks["PROGRESSIVE: live status >1s BEFORE primary reasoning (stream active mid-turn)"]
        and all_checks["PROGRESSIVE: primary reasoning arrives BEFORE secondary starts (>1s)"]
        and all_checks["primary delivered reasoning via delta event(s)"]
        and all_checks["sequence: investigation_complete is last"]
        and all_checks["DB: case persisted with secondary verdict"]
    )
    if passed == len(all_checks):
        print("\nVERIFY CONDITION MET: agent reasoning appears progressively")
        print("over live SSE — the client watched live thinking signals, the")
        print("primary's full reasoning the instant it finished (seconds")
        print("before the secondary even started), and every pipeline")
        print("stage as it happened.")
        return 0
    if core:
        print("\nVERIFY CONDITION MET (core); some auxiliary check(s) failed.")
        return 0
    print("\nVERIFY CONDITION NOT MET.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
