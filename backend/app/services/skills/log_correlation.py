"""Skill 6c — Log/event correlation.

Analyzes log entries within an alert payload to find patterns,
temporal sequences, and multi-event attack chains.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_timestamp(ts: str) -> datetime | None:
    """Try to parse an ISO-8601 timestamp string."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _extract_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract log entries from the payload."""
    entries = payload.get("log_entries", [])
    if not isinstance(entries, list):
        return []

    parsed = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ts = _parse_timestamp(entry.get("timestamp", ""))
        parsed.append({
            "timestamp": ts,
            "event": entry.get("event", "unknown"),
            "raw": entry,
        })

    # Sort by timestamp
    parsed.sort(key=lambda e: e["timestamp"] or datetime.min)
    return parsed


def _detect_attack_chain(events: list[dict[str, Any]]) -> list[str]:
    """Identify multi-stage attack patterns in event sequences."""
    findings: list[str] = []
    event_names = [e["event"].lower() for e in events]
    event_text = " ".join(event_names)

    # Pattern: Reconnaissance → Exploitation → Payload delivery
    recon_keywords = ["scan", "enumeration", "probe", "syn"]
    exploit_keywords = ["exploit", "overflow", "injection", "bypass"]
    payload_keywords = ["download", "write", "install", "execute", "process_create"]

    has_recon = any(kw in event_text for kw in recon_keywords)
    has_exploit = any(kw in event_text for kw in exploit_keywords)
    has_payload = any(kw in event_text for kw in payload_keywords)

    if has_recon and has_payload:
        findings.append(
            "Attack chain detected: Reconnaissance → Payload delivery "
            "(scanning followed by file/process activity)"
        )

    # Pattern: Authentication brute force
    auth_events = [e for e in events if "failed" in e["event"].lower() or "password" in e["event"].lower()]
    if len(auth_events) >= 2:
        findings.append(
            f"Brute force pattern: {len(auth_events)} authentication failure events detected"
        )

    # Pattern: Process spawn → network connection → file write (dropper chain)
    process_events = [e for e in events if "process" in e["event"].lower()]
    network_events = [e for e in events if "network" in e["event"].lower() or "connection" in e["event"].lower()]
    file_events = [e for e in events if "file" in e["event"].lower() or "write" in e["event"].lower()]

    if process_events and network_events and file_events:
        findings.append(
            "Dropper chain detected: Process creation → Network connection → File write"
        )

    # Pattern: DNS query to suspicious domain → large outbound transfer
    dns_events = [e for e in events if "dns" in e["event"].lower()]
    transfer_events = [e for e in events if "transfer" in e["event"].lower() or "outbound" in e["event"].lower()]

    if dns_events and transfer_events:
        findings.append(
            "Exfiltration pattern: DNS query followed by outbound data transfer"
        )

    return findings


def _temporal_analysis(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze the timing of events."""
    timed_events = [e for e in events if e["timestamp"] is not None]
    if len(timed_events) < 2:
        return {"span": "N/A", "event_count": len(events), "note": "Insufficient timestamps for temporal analysis"}

    first = timed_events[0]["timestamp"]
    last = timed_events[-1]["timestamp"]
    span = last - first

    # Calculate event rate
    span_seconds = span.total_seconds()
    rate = len(timed_events) / span_seconds if span_seconds > 0 else float("inf")

    return {
        "span": str(span),
        "span_seconds": span_seconds,
        "first_event": str(first),
        "last_event": str(last),
        "event_count": len(timed_events),
        "events_per_second": round(rate, 2) if rate != float("inf") else "burst",
        "note": (
            "Rapid burst activity" if rate > 1
            else "Sustained activity" if span_seconds > 600
            else "Brief activity window"
        ),
    }


def _unique_entities(payload: dict[str, Any]) -> dict[str, list[str]]:
    """Extract unique IPs, hosts, users from the payload."""
    text = str(payload)
    entities: dict[str, list[str]] = {
        "source_ips": [],
        "destination_ips": [],
        "hosts": [],
        "users": [],
    }

    # From top-level payload fields
    for field, key in [
        ("source_ip", "source_ips"),
        ("destination_ip", "destination_ips"),
        ("hostname", "hosts"),
        ("user", "users"),
    ]:
        val = payload.get(field)
        if val and val not in entities[key]:
            entities[key].append(val)

    # From log entries
    for entry in payload.get("log_entries", []):
        if not isinstance(entry, dict):
            continue
        for field, key in [("src", "source_ips"), ("dst", "destination_ips"), ("dst_ip", "destination_ips")]:
            val = entry.get(field)
            if val and val not in entities[key]:
                entities[key].append(val)
        user = entry.get("user")
        if user and user not in entities["users"]:
            entities["users"].append(user)

    return entities


def correlate_logs(alert_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run log/event correlation on the alert payload.

    Returns a structured correlation report.
    """
    events = _extract_events(payload)
    chains = _detect_attack_chain(events)
    temporal = _temporal_analysis(events)
    entities = _unique_entities(payload)

    # Build summary
    summary_parts = [f"Analyzed {len(events)} log entries"]
    if chains:
        summary_parts.append(f"{len(chains)} attack pattern(s) detected")
    if temporal.get("note"):
        summary_parts.append(temporal["note"])

    return {
        "event_count": len(events),
        "events": [{"timestamp": str(e["timestamp"]), "event": e["event"]} for e in events],
        "attack_chains": chains,
        "temporal_analysis": temporal,
        "entities_involved": entities,
        "summary": " | ".join(summary_parts),
    }
