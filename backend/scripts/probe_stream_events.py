"""Probe: what does the Qoder session stream ACTUALLY emit during a turn?

Phase 14 follow-up — the first test run showed each agent's full response
arriving as a single agent.message event.  This probe runs one real
investigation turn and logs EVERY stream event with a timestamp, so we
can see whether anything flows between session start and the final
message (status changes, tool activity) that the SSE relay should
surface.
"""

import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.qoder_client import get_qoder_client
from app.services.skills import enrich_iocs

ALERT = {
    "source_alert_id": "PROBE-001",
    "alert_type": "brute_force_login",
    "raw_payload": {
        "source_ip": "198.51.100.23",
        "destination_ip": "10.0.1.15",
        "destination_port": 22,
        "protocol": "TCP",
        "target_service": "SSH",
        "failed_attempts": 240,
        "time_window_seconds": 300,
        "unique_usernames_tried": 9,
        "geo_ip": {"country": "RU", "city": "Moscow"},
        "description": "SSH brute force probe",
        "iocs": ["198.51.100.23"],
    },
}


def main() -> None:
    qoder = get_qoder_client()
    payload = ALERT["raw_payload"]

    prompt = (
        "Investigate this security alert briefly (2-3 sentences verdict):\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```\n"
        f"OTX enrichment: {json.dumps(enrich_iocs(payload), indent=2)}\n\n"
        "End with a line: **Verdict:** true_positive or false_positive"
    )

    session = qoder.create_session()
    sid = session.get("id", session.get("session_id", ""))
    print(f"session {sid}")
    qoder.send_message(sid, prompt)

    t0 = time.time()
    counts: dict[str, int] = {}
    n_delta = 0
    for event in qoder.stream_session_events(sid, timeout=180):
        elapsed = time.time() - t0
        if event["type"] == "delta":
            n_delta += 1
            counts["delta"] = counts.get("delta", 0) + 1
            print(f"  t={elapsed:6.1f}s  DELTA  {len(event['text'])} chars")
        else:
            name = event.get("event") or "unknown"
            counts[name] = counts.get(name, 0) + 1
            data = json.dumps(event.get("data", {}))[:160]
            print(f"  t={elapsed:6.1f}s  STATUS {name:28s} {data}")

    print(f"\nevent counts: {counts}")


if __name__ == "__main__":
    main()
