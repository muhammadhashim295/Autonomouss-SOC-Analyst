"""Skill 6d — Behavioral-deviation heuristic.

Flags indicators that deviate from common baseline patterns:
unusual timing, abnormal volumes, unexpected geo-locations,
suspicious process hierarchies, and critical-asset targeting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


# ── Baseline thresholds ──────────────────────────────────────────────────

_FAILED_LOGIN_THRESHOLD = 10       # More than 10 failures is suspicious
_BYTES_TRANSFER_THRESHOLD = 104_857_600  # 100 MB
_OFF_BUSINESS_HOURS = (22, 6)      # 10 PM to 6 AM = off-hours
_SUSPICIOUS_PORTS = {4444, 5555, 8888, 1337, 31337, 1234, 6667, 6697}
_SUSPICIOUS_PROCESS_PARENTS = {
    "winword.exe", "excel.exe", "powerpnt.exe",  # Office macros
    "outlook.exe", "wscript.exe", "cscript.exe",  # Scripting hosts
    "mshta.exe", "certutil.exe",                   # LOLBins
}
_CRITICAL_ASSET_TAGS = {"critical-asset", "domain-controller", "prod-db", "exec-account"}


def _check_timing(payload: dict[str, Any]) -> list[str]:
    """Flag off-business-hours activity."""
    flags: list[str] = []
    log_entries = payload.get("log_entries", [])

    for entry in log_entries:
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
            if ts.hour >= _OFF_BUSINESS_HOURS[0] or ts.hour < _OFF_BUSINESS_HOURS[1]:
                flags.append(
                    f"Off-hours activity: event at {ts_str} "
                    f"({ts.strftime('%H:%M')} is outside business hours 06:00-22:00)"
                )
                break  # One flag is enough
        except ValueError:
            continue

    return flags


def _check_volume(payload: dict[str, Any]) -> list[str]:
    """Flag abnormal volumes."""
    flags: list[str] = []

    # Failed login attempts
    failed = payload.get("failed_attempts", 0)
    if failed > _FAILED_LOGIN_THRESHOLD:
        flags.append(
            f"High failure rate: {failed} failed attempts "
            f"(threshold: {_FAILED_LOGIN_THRESHOLD})"
        )

    # Data transfer volume
    bytes_sent = payload.get("bytes_sent", 0)
    if bytes_sent > _BYTES_TRANSFER_THRESHOLD:
        mb = bytes_sent / (1024 * 1024)
        flags.append(
            f"Large data transfer: {mb:.1f} MB sent "
            f"(threshold: {_BYTES_TRANSFER_THRESHOLD / (1024*1024):.0f} MB)"
        )

    # Duration anomalies
    duration = payload.get("duration_seconds", 0)
    if duration > 3600 and bytes_sent > _BYTES_TRANSFER_THRESHOLD:
        flags.append(
            f"Sustained exfiltration: {mb:.1f} MB over {duration/60:.0f} minutes"
        )

    # Unique usernames in brute force
    usernames = payload.get("unique_usernames_tried", 0)
    if usernames > 5:
        flags.append(
            f"Username enumeration: {usernames} unique usernames tried "
            f"(indicates dictionary/spray attack)"
        )

    return flags


def _check_geo(payload: dict[str, Any]) -> list[str]:
    """Flag suspicious geographic origins."""
    flags: list[str] = []
    geo = payload.get("geo_ip", {})

    if geo:
        country = geo.get("country", "unknown")
        city = geo.get("city", "unknown")
        asn = geo.get("asn", "unknown")
        flags.append(
            f"External origin: {city}, {country} (ASN: {asn})"
        )

    # Check for known suspicious patterns in destination
    dest_ip = payload.get("destination_ip", "")
    description = payload.get("description", "").lower()

    if "tor" in description or "onion" in description:
        flags.append("Connection to Tor network or onion service detected")

    return flags


def _check_process_hierarchy(payload: dict[str, Any]) -> list[str]:
    """Flag suspicious parent→child process chains."""
    flags: list[str] = []

    parent = payload.get("parent_process", "").lower()
    process = payload.get("process_name", "").lower()
    cmdline = payload.get("command_line", "").lower()

    # Office app spawning script interpreter
    if parent in _SUSPICIOUS_PROCESS_PARENTS:
        flags.append(
            f"Suspicious process chain: {parent} → {process} "
            f"(office/scripting host spawning interpreter)"
        )

    # Suspicious command-line flags
    suspicious_flags = ["-enc", "-encodedcommand", "-w hidden", "-windowstyle hidden",
                        "-nop", "-noprofile", "-exec bypass", "downloadstring", "iex"]
    found_flags = [f for f in suspicious_flags if f in cmdline]
    if found_flags:
        flags.append(
            f"Suspicious command-line flags: {', '.join(found_flags)}"
        )

    # Encoded payload detection
    if "-enc" in cmdline or "-encodedcommand" in cmdline:
        flags.append("Encoded PowerShell payload detected — common in malware delivery")

    return flags


def _check_network(payload: dict[str, Any]) -> list[str]:
    """Flag suspicious network indicators."""
    flags: list[str] = []

    port = payload.get("destination_port")
    if port and port in _SUSPICIOUS_PORTS:
        flags.append(f"Connection on suspicious port: {port}")

    # DNS anomalies
    for entry in payload.get("log_entries", []):
        query = entry.get("query", "")
        if "onion" in query.lower() or "dark" in query.lower():
            flags.append(f"Suspicious DNS query: {query}")

    return flags


def _check_asset_criticality(payload: dict[str, Any]) -> list[str]:
    """Flag if the target is a critical asset."""
    flags: list[str] = []

    asset_tags = set(payload.get("asset_tags", []))
    critical = asset_tags & _CRITICAL_ASSET_TAGS

    if critical:
        flags.append(
            f"Critical asset targeted: tags = {', '.join(critical)}"
        )

    hostname = payload.get("hostname", "")
    if any(kw in hostname.upper() for kw in ["DC", "SRV-DC", "DOMAIN", "AD-"]):
        flags.append(f"Domain controller targeted: {hostname}")

    return flags


def detect_deviation(alert_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run behavioral-deviation heuristics on the alert payload.

    Returns a structured report with all deviation flags.
    """
    all_flags: list[str] = []

    checks = {
        "timing": _check_timing(payload),
        "volume": _check_volume(payload),
        "geography": _check_geo(payload),
        "process_hierarchy": _check_process_hierarchy(payload),
        "network": _check_network(payload),
        "asset_criticality": _check_asset_criticality(payload),
    }

    for category, flags in checks.items():
        all_flags.extend(flags)

    # Calculate deviation score (0.0 - 1.0)
    score = min(1.0, len(all_flags) * 0.15)

    return {
        "deviation_score": round(score, 2),
        "flag_count": len(all_flags),
        "flags_by_category": checks,
        "all_flags": all_flags,
        "is_high_deviation": score >= 0.5,
        "summary": (
            f"Deviation score: {score:.2f} ({len(all_flags)} flag(s))"
            + (" — HIGH DEVIATION" if score >= 0.5 else "")
        ),
    }
