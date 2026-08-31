"""Skill 6b — MITRE ATT&CK technique mapping.

Maps alert types, indicators, and behavioral patterns to specific
MITRE ATT&CK techniques and tactics.
"""

from __future__ import annotations

from typing import Any


# ── ATT&CK mapping rules ─────────────────────────────────────────────────
# Each rule maps a pattern (in alert_type, payload keys, or descriptions)
# to a specific ATT&CK technique.

_ATTACK_RULES: list[dict[str, Any]] = [
    # ── Initial Access ────────────────────────────────────────────────
    {
        "technique_id": "T1566.001",
        "technique_name": "Phishing: Spearphishing Attachment",
        "tactic": "Initial Access",
        "triggers": {
            "alert_types": ["suspicious_process_execution"],
            "parent_processes": ["winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe"],
            "keywords": ["macro", "dropper", "attachment"],
        },
    },
    {
        "technique_id": "T1190",
        "technique_name": "Exploit Public-Facing Application",
        "tactic": "Initial Access",
        "triggers": {
            "alert_types": ["web_attack", "sql_injection", "xss"],
            "keywords": ["exploit", "vulnerability", "web shell"],
        },
    },
    # ── Execution ─────────────────────────────────────────────────────
    {
        "technique_id": "T1059.001",
        "technique_name": "Command and Scripting Interpreter: PowerShell",
        "tactic": "Execution",
        "triggers": {
            "process_names": ["powershell.exe", "pwsh.exe"],
            "keywords": ["powershell", "-enc", "-encodedcommand", "downloadstring", "iex"],
        },
    },
    # ── Credential Access ─────────────────────────────────────────────
    {
        "technique_id": "T1110.001",
        "technique_name": "Brute Force: Password Guessing",
        "tactic": "Credential Access",
        "triggers": {
            "alert_types": ["brute_force_login", "authentication_failure"],
            "keywords": ["brute force", "failed login", "password guessing", "failed password"],
            "payload_keys": ["failed_attempts"],
        },
    },
    {
        "technique_id": "T1110.003",
        "technique_name": "Brute Force: Password Spraying",
        "tactic": "Credential Access",
        "triggers": {
            "alert_types": ["brute_force_login"],
            "payload_keys": ["unique_usernames_tried"],
            "min_unique_usernames": 5,
        },
    },
    # ── Lateral Movement ──────────────────────────────────────────────
    {
        "technique_id": "T1021.001",
        "technique_name": "Remote Services: Remote Desktop Protocol",
        "tactic": "Lateral Movement",
        "triggers": {
            "destination_ports": [3389],
            "keywords": ["rdp", "remote desktop"],
        },
    },
    {
        "technique_id": "T1021.004",
        "technique_name": "Remote Services: SSH",
        "tactic": "Lateral Movement",
        "triggers": {
            "destination_ports": [22],
            "alert_types": ["brute_force_login"],
        },
    },
    # ── Collection ────────────────────────────────────────────────────
    {
        "technique_id": "T1005",
        "technique_name": "Data from Local System",
        "tactic": "Collection",
        "triggers": {
            "alert_types": ["data_exfiltration"],
            "keywords": ["data exfiltration", "data theft"],
        },
    },
    # ── Exfiltration ──────────────────────────────────────────────────
    {
        "technique_id": "T1048.001",
        "technique_name": "Exfiltration Over Alternative Protocol: Exfiltration Over Symmetric Encrypted Non-C2 Protocol",
        "tactic": "Exfiltration",
        "triggers": {
            "alert_types": ["data_exfiltration"],
            "keywords": ["tor", "onion", "darkrelay"],
        },
    },
    {
        "technique_id": "T1041",
        "technique_name": "Exfiltration Over C2 Channel",
        "tactic": "Exfiltration",
        "triggers": {
            "keywords": ["c2", "command and control", "beacon"],
            "payload_keys": ["bytes_sent"],
            "min_bytes": 104857600,  # 100 MB
        },
    },
    # ── Discovery ─────────────────────────────────────────────────────
    {
        "technique_id": "T1046",
        "technique_name": "Network Service Scanning",
        "tactic": "Discovery",
        "triggers": {
            "alert_types": ["vulnerability_scan", "port_scan"],
            "keywords": ["scan", "enumeration", "qualys", "nessus"],
        },
    },
    # ── Defense Evasion ───────────────────────────────────────────────
    {
        "technique_id": "T1027",
        "technique_name": "Obfuscated Files or Information",
        "tactic": "Defense Evasion",
        "triggers": {
            "keywords": ["encoded", "-enc", "-w hidden", "bypass", "base64"],
        },
    },
    # ── Command and Control ───────────────────────────────────────────
    {
        "technique_id": "T1071.001",
        "technique_name": "Application Layer Protocol: Web Protocols",
        "tactic": "Command and Control",
        "triggers": {
            "keywords": ["c2", "beacon", "callback"],
            "payload_keys": ["dst_ip"],
        },
    },
    {
        "technique_id": "T1573",
        "technique_name": "Encrypted Channel",
        "tactic": "Command and Control",
        "triggers": {
            "keywords": ["tor", "onion", "encrypted tunnel"],
        },
    },
]


def _text_matches(payload: dict[str, Any], keywords: list[str]) -> bool:
    """Check if any keyword appears in the alert text."""
    text = str(payload).lower()
    return any(kw.lower() in text for kw in keywords)


def _check_rule(rule: dict[str, Any], alert_type: str, payload: dict[str, Any]) -> bool:
    """Evaluate a single ATT&CK rule against the alert."""
    triggers = rule["triggers"]

    # Check alert_type match
    if "alert_types" in triggers:
        if alert_type.lower() not in [t.lower() for t in triggers["alert_types"]]:
            # Don't reject yet — other triggers might match
            pass
        else:
            return True

    # Check process names
    if "process_names" in triggers:
        proc = payload.get("process_name", "").lower()
        if proc in [p.lower() for p in triggers["process_names"]]:
            return True

    # Check parent processes (phishing)
    if "parent_processes" in triggers:
        parent = payload.get("parent_process", "").lower()
        if parent in [p.lower() for p in triggers["parent_processes"]]:
            return True

    # Check destination ports
    if "destination_ports" in triggers:
        port = payload.get("destination_port")
        if port in triggers["destination_ports"]:
            return True

    # Check payload keys
    if "payload_keys" in triggers:
        for key in triggers["payload_keys"]:
            if key in payload:
                # Check minimum thresholds if specified
                if key == "failed_attempts" and "min_failed" in triggers:
                    if payload[key] >= triggers["min_failed"]:
                        return True
                elif key == "unique_usernames_tried" and "min_unique_usernames" in triggers:
                    if payload[key] >= triggers["min_unique_usernames"]:
                        return True
                elif key == "bytes_sent" and "min_bytes" in triggers:
                    if payload[key] >= triggers["min_bytes"]:
                        return True
                else:
                    return True

    # Check keywords
    if "keywords" in triggers:
        if _text_matches(payload, triggers["keywords"]):
            return True

    return False


def map_attack_techniques(alert_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Map an alert to relevant MITRE ATT&CK techniques.

    Returns a structured report with matched techniques and tactics.
    """
    matched: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for rule in _ATTACK_RULES:
        if rule["technique_id"] in seen_ids:
            continue
        if _check_rule(rule, alert_type, payload):
            matched.append({
                "technique_id": rule["technique_id"],
                "technique_name": rule["technique_name"],
                "tactic": rule["tactic"],
            })
            seen_ids.add(rule["technique_id"])

    # Group by tactic
    by_tactic: dict[str, list[str]] = {}
    for m in matched:
        tactic = m["tactic"]
        if tactic not in by_tactic:
            by_tactic[tactic] = []
        by_tactic[tactic].append(f"{m['technique_id']} — {m['technique_name']}")

    return {
        "matched_techniques": matched,
        "by_tactic": by_tactic,
        "technique_count": len(matched),
        "summary": (
            f"Mapped to {len(matched)} ATT&CK technique(s): "
            + ", ".join(f"{m['technique_id']} ({m['tactic']})" for m in matched)
            if matched
            else "No ATT&CK techniques matched."
        ),
    }
