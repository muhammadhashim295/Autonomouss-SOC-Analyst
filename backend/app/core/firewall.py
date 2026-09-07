"""Log-poisoning firewall — sanitisation / validation layer.

Runs **before** any alert content reaches either agent.  Detects:

* Prompt-injection patterns embedded in log/alert text fields
* System-prompt mimicking (``<system>``, ``[INST]``, role directives)
* Role-play / persona-override attempts
* Suspicious encoding (high ratio of non-ASCII or control characters)
* Structural issues (missing or wrong-type required fields)

Flagged alerts are **never silently dropped** — they are always inserted into
the ``alerts`` table *and* recorded in ``firewall_flags`` so that a poisoned
log cannot cause an alert to disappear.

This is real enforced code, not a prompt-level instruction.
"""

from __future__ import annotations

import re
from typing import Any


# ── Injection-pattern signatures ──────────────────────────────────────────────
# Each tuple is (compiled regex, human-readable flag reason).

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Explicit instruction-override phrases
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
     "Prompt injection: instruction override"),
    (re.compile(r"ignore\s+(all\s+)?above\s+instructions", re.I),
     "Prompt injection: instruction override (above)"),
    (re.compile(r"disregard\s+(all\s+)?(previous|prior|earlier)\s+(instructions|rules|policies)", re.I),
     "Prompt injection: disregard instructions"),
    (re.compile(r"forget\s+(all\s+)?(previous|prior|earlier)\s+(instructions|context)", re.I),
     "Prompt injection: forget instructions"),

    # Verdict / action manipulation
    (re.compile(r"close\s+this\s+alert\s+as\s+(a\s+)?false[\s_-]?positive", re.I),
     "Prompt injection: verdict manipulation"),
    (re.compile(r"set\s+verdict\s+to", re.I),
     "Prompt injection: verdict directive"),
    (re.compile(r"mark\s+as\s+(false[\s_-]?positive|safe|benign)", re.I),
     "Prompt injection: classification directive"),

    # System-prompt / role mimicking
    (re.compile(r"<\s*system\s*>", re.I),
     "System prompt mimicry: <system> tag"),
    (re.compile(r"<\s*/?\s*assistant\s*>", re.I),
     "System prompt mimicry: <assistant> tag"),
    (re.compile(r"\[\s*INST\s*\]", re.I),
     "System prompt mimicry: [INST] tag"),
    (re.compile(r"\[\s*SYSTEM\s*\]", re.I),
     "System prompt mimicry: [SYSTEM] tag"),
    (re.compile(r"you\s+are\s+now\s+in\s+\w+\s+mode", re.I),
     "Role-play: mode override"),
    (re.compile(r"act\s+as\s+(if\s+)?(you\s+are\s+)?a", re.I),
     "Role-play: persona directive"),
    (re.compile(r"new\s+instructions?\s*:", re.I),
     "Role-play: new instructions"),
    (re.compile(r"override\s*:\s*", re.I),
     "Role-play: override directive"),

    # Maintenance / safe-mode claims
    (re.compile(r"maintenance\s+mode", re.I),
     "Role-play: maintenance mode claim"),
    (re.compile(r"this\s+is\s+a\s+(safe|test|known|trusted)\s+(alert|input|message)", re.I),
     "Role-play: safe-input claim"),

    # Confidence / decision manipulation
    (re.compile(r"with\s+high\s+confidence.*close", re.I),
     "Prompt injection: confidence manipulation"),
    (re.compile(r"do\s+not\s+(investigate|analyse|analyze|process|escalate)", re.I),
     "Prompt injection: action suppression"),
]


# ── Public API ────────────────────────────────────────────────────────────────


def check_alert(source_alert_id: str, alert_type: str, raw_payload: dict[str, Any]) -> list[str]:
    """Scan an alert's content for poisoning indicators.

    Parameters
    ----------
    source_alert_id : str
        External alert identifier (not scanned — treated as opaque).
    alert_type : str
        Alert classification (not scanned — treated as opaque).
    raw_payload : dict
        The full JSON payload — every string value (including nested) is
        scanned for injection patterns.

    Returns
    -------
    list[str]
        Human-readable flag reasons.  Empty list means the alert passed clean.
    """
    flags: list[str] = []

    # 1. Structural validation
    if not raw_payload or not isinstance(raw_payload, dict):
        flags.append("Structural: raw_payload is empty or not a JSON object")
        return flags

    # 2. Pattern-based injection detection (recursive scan of all string values)
    for text in _extract_strings(raw_payload):
        for pattern, reason in _INJECTION_PATTERNS:
            if pattern.search(text):
                flags.append(reason)

    # 3. Encoding anomalies
    encoding_flags = _check_encoding(raw_payload)
    flags.extend(encoding_flags)

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_strings(obj: Any) -> list[str]:
    """Recursively extract all string keys and values from a nested dict / list."""
    strings: list[str] = []
    if isinstance(obj, str):
        strings.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                strings.append(k)
            strings.extend(_extract_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            strings.extend(_extract_strings(item))
    return strings


def _check_encoding(obj: Any) -> list[str]:
    """Detect unusual encoding patterns in string values."""
    flags: list[str] = []
    for text in _extract_strings(obj):
        if not text:
            continue

        # High ratio of non-ASCII / non-printable characters (excluding normal
        # Unicode like em-dashes, accented chars, etc.)
        if len(text) > 10:
            non_printable = sum(1 for c in text if not c.isprintable() and c not in "\n\r\t")
            ratio = non_printable / len(text)
            if ratio > 0.15:
                flags.append(f"Encoding anomaly: {ratio:.0%} non-printable characters")

        # Null bytes (common in injection attempts)
        if "\x00" in text:
            flags.append("Encoding anomaly: null byte detected")

        # Unicode homoglyph abuse — Cyrillic/Greek chars mixed with Latin
        if re.search(r"[\u0400-\u04FF\u0370-\u03FF]", text) and re.search(r"[a-zA-Z]", text):
            # Only flag if the non-Latin chars appear inside what looks like
            # normal English text (not a legitimate mixed-language string)
            latin_ratio = sum(1 for c in text if c.isascii()) / len(text)
            if 0.3 < latin_ratio < 0.9:
                flags.append("Encoding anomaly: mixed-script homoglyph suspicion")

    return flags


def sanitize_snippet(text: str, max_length: int = 500) -> str:
    """Produce a safe, truncated snippet for storage in ``firewall_flags``."""
    # Strip non-printable chars for safe storage
    clean = "".join(c if c.isprintable() or c in "\n\r\t" else "?" for c in text)
    if len(clean) > max_length:
        clean = clean[:max_length] + "…"
    return clean
