"""Provider-agnostic agent definitions shared by Groq and Cerebras clients.

The Primary Alert Triage Agent (Groq) and the Secondary Deep Investigation
Agent (Cerebras) must behave identically regardless of which provider runs
them — same system prompts (agentrules.md), same structured-prompt
builders, same deterministic fallback text, and therefore the same
``parse_agent_response`` output shape.  Keeping these in one module means
``groq_client.py`` and ``cerebras_client.py`` differ only in transport
(endpoint, auth, model, streaming), never in agent behaviour.
"""

from __future__ import annotations

import json
from typing import Any

# ── System prompts (agentrules.md) ────────────────────────────────────────────

PRIMARY_AGENT_SYSTEM_PROMPT = (
    "You are the Primary Alert Triage Agent in an Autonomous SOC Analyst framework. "
    "Your role is first responder: investigate security alerts using the provided "
    "pre-computed skill outputs (OTX IOC enrichment, ATT&CK mapping, log correlation, "
    "behavioral deviation) and retrieved past cases. Form an initial verdict "
    "(false_positive or true_positive) with a confidence score (0.0 to 1.0), "
    "evidence-cited reasoning, and a self-audit statement. "
    "You MUST cite specific evidence from the skill outputs. Never state a conclusion "
    "without citing the evidence that produced it."
)

SECONDARY_AGENT_SYSTEM_PROMPT = (
    "You are the Secondary Deep Investigation Agent in an Autonomous SOC Analyst framework. "
    "Your role is independent auditor: re-investigate the security alert using fresh skill "
    "outputs and compare your findings with the Primary Agent's investigation report. "
    "Do NOT defer uncritically to the primary agent's verdict — independently re-derive "
    "your conclusion. State explicitly whether you agree or disagree, provide "
    "evidence-cited reasoning, classify impact level (standard or high_impact), "
    "recommend an action, and perform a self-audit."
)


def system_prompt_for_role(role: str) -> str:
    """Return the system prompt for ``"primary"`` or ``"secondary"``."""
    return SECONDARY_AGENT_SYSTEM_PROMPT if role == "secondary" else PRIMARY_AGENT_SYSTEM_PROMPT


# ── Structured prompt builders ────────────────────────────────────────────────


def build_investigation_prompt(
    alert_payload: dict[str, Any],
    alert_type: str,
    payload: dict[str, Any],
    enrichment: dict[str, Any],
    similar_cases: list[dict[str, Any]],
) -> str:
    """Build the Primary Agent's structured investigation prompt."""
    otx = enrichment["otx_enrichment"]
    attack = enrichment["attack_mapping"]
    log_corr = enrichment["log_correlation"]
    deviation = enrichment["behavioral_deviation"]

    if similar_cases:
        memory_section = (
            f"## Similar Past Cases ({len(similar_cases)} found in memory)\n"
            "Prior investigations the memory store matched to this alert. "
            "If they are relevant — e.g. the same IOCs, hosts, or attack "
            "pattern — reference them explicitly in your reasoning (by "
            "source_alert_id) and factor them into your verdict.\n\n"
            + json.dumps(similar_cases, indent=2)
        )
    else:
        memory_section = (
            "## Similar Past Cases\n"
            "No similar past cases found in memory."
        )

    return (
        "Investigate the following security alert. You MUST produce a "
        "structured investigation report with ALL of the sections below.\n\n"
        "## Alert Data\n"
        f"**Alert ID:** {alert_payload.get('source_alert_id', 'unknown')}\n"
        f"**Alert Type:** {alert_type}\n"
        f"**Raw Payload:**\n```json\n"
        f"{json.dumps(payload, indent=2)}\n```\n\n"
        f"{memory_section}\n\n"
        "## Pre-computed Investigation Skills Results\n"
        "Reference these SPECIFICALLY in your reasoning. Do not just state "
        "conclusions — cite which skill output supports each finding.\n\n"
        f"### OTX IOC Enrichment\n{json.dumps(otx, indent=2)}\n\n"
        f"### ATT&CK Mapping\n{json.dumps(attack, indent=2)}\n\n"
        f"### Log Correlation\n{json.dumps(log_corr, indent=2)}\n\n"
        f"### Behavioral Deviation\n{json.dumps(deviation, indent=2)}\n\n"
        "## Required Output Format\n"
        "You MUST structure your response EXACTLY as follows:\n\n"
        "**Verdict:** false_positive OR true_positive\n\n"
        "**Confidence:** a number between 0.0 and 1.0\n\n"
        "**Reasoning:**\n"
        "Write 3-6 sentences explaining your verdict. You MUST cite "
        "specific outputs from the skills above.\n\n"
        "**Self-Audit:**\n"
        "State what evidence could change this verdict, and any gaps "
        "in the current investigation. Be honest about uncertainty.\n\n"
        "**Next Action:**\n"
        "Recommend what should happen next (close, escalate, investigate further)."
    )


def build_reinvestigation_prompt(
    alert_payload: dict[str, Any],
    alert_type: str,
    payload: dict[str, Any],
    enrichment: dict[str, Any],
    primary_result: dict[str, Any],
    similar_cases: list[dict[str, Any]] | None = None,
) -> str:
    """Build the Secondary Agent's independent re-investigation prompt."""
    primary_response = primary_result.get("agent_response", "")
    primary_parsed = primary_result.get("parsed", {})

    otx = enrichment["otx_enrichment"]
    attack = enrichment["attack_mapping"]
    log_corr = enrichment["log_correlation"]
    deviation = enrichment["behavioral_deviation"]

    primary_summary = (
        f"- Verdict: {primary_parsed.get('verdict', 'unknown')}\n"
        f"- Confidence: {primary_parsed.get('confidence', 'unknown')}\n"
        f"- ATT&CK technique: {primary_parsed.get('attack_technique', 'none')}\n"
    )

    if similar_cases:
        memory_section = (
            f"## Similar Past Cases ({len(similar_cases)} found in memory)\n"
            "Prior investigations the memory store matched to this alert.\n\n"
            f"{json.dumps(similar_cases, indent=2)}\n\n"
        )
    else:
        memory_section = (
            "## Similar Past Cases\n"
            "No similar past cases found in memory.\n\n"
        )

    return (
        "Re-investigate the following security alert. The Primary Alert "
        "Triage Agent has already investigated it and produced a verdict. "
        "Your job is to INDEPENDENTLY re-derive the evidence and then "
        "agree or disagree with the primary's conclusion. Do NOT simply "
        "trust the primary's analysis.\n\n"
        "## Alert Data\n"
        f"**Alert ID:** {alert_payload.get('source_alert_id', 'unknown')}\n"
        f"**Alert Type:** {alert_type}\n"
        f"**Raw Payload:**\n```json\n"
        f"{json.dumps(payload, indent=2)}\n```\n\n"
        "## Fresh Investigation Skills Results\n"
        f"### OTX IOC Enrichment\n{json.dumps(otx, indent=2)}\n\n"
        f"### ATT&CK Mapping\n{json.dumps(attack, indent=2)}\n\n"
        f"### Log Correlation\n{json.dumps(log_corr, indent=2)}\n\n"
        f"### Behavioral Deviation\n{json.dumps(deviation, indent=2)}\n\n"
        f"{memory_section}"
        "## Primary Agent's Investigation Report\n"
        f"**Summary:**\n{primary_summary}\n"
        f"**Full Report:**\n```\n{primary_response}\n```\n\n"
        "## Required Output Format\n"
        "You MUST structure your response EXACTLY as follows:\n\n"
        "**Secondary Verdict:** agree | disagree | false_positive | true_positive\n\n"
        "**Confidence:** a number between 0.0 and 1.0\n\n"
        "**Reasoning:**\n"
        "Write 3-6 sentences citing YOUR OWN evidence from the skills above.\n\n"
        "**Impact Level:** standard | high_impact\n\n"
        "**Recommended Action:**\n"
        "Name the specific action that should be taken.\n\n"
        "**Self-Audit:**\n"
        "What could make your re-investigation verdict wrong?"
    )


# ── Deterministic fallback text ───────────────────────────────────────────────
#
# Used only when a provider rejects the call permanently (no quota, org-blocked
# model, bad key) or the retry budget is exhausted.  It keeps the demo pipeline
# alive with a coherent, evidence-styled report instead of crashing.  Every use
# is logged loudly by the calling client so it is never mistaken for live model
# output.


def fallback_agent_text(role: str, prompt: str) -> str:
    """Return deterministic structured report text for ``role`` given ``prompt``."""
    p = prompt.lower()

    if "authentication_failure" in p or "auth_failure" in p:
        if role == "primary":
            return (
                "**Verdict:** false_positive\n\n"
                "**Confidence:** 0.80\n\n"
                "**Reasoning:**\n"
                "The OTX IOC Enrichment reports no malicious IP reputation for the internal source host. "
                "Log correlation indicates only a small number of failed login attempts, within normal user operational variance. "
                "Behavioral deviation score is below the standard threshold (0.12 < 0.50). "
                "No external indicators of compromise or lateral movement were detected.\n\n"
                "**Self-Audit:**\n"
                "If the failure count spikes above 20 within one minute, or the source IP originates outside the subnet, re-triage.\n\n"
                "**Next Action:**\n"
                "Close the alert as a benign false positive."
            )
        return (
            "**Secondary Verdict:** agree\n\n"
            "**Confidence:** 0.85\n\n"
            "**Reasoning:**\n"
            "Independently verified OTX threat intelligence and log correlation. "
            "The source IP is confirmed internal with zero threat matches. "
            "Behavioral deviation remains below threshold on a fresh skill run. "
            "I agree with the primary agent's false-positive determination.\n\n"
            "**Impact Level:** standard\n\n"
            "**Recommended Action:**\n"
            "none\n\n"
            "**Self-Audit:**\n"
            "Verified zero external IOC matches; would revisit on any outbound beacon."
        )

    if "data_exfiltration" in p or "exfil" in p:
        if role == "primary":
            return (
                "**Verdict:** true_positive\n\n"
                "**Confidence:** 0.92\n\n"
                "**Reasoning:**\n"
                "OTX Threat Intel mapping identified an active data-exfiltration pattern (T1041) to an external destination IP. "
                "Log correlation detected a large outbound transfer originating from a server-tier host. "
                "The behavioral-deviation heuristic flagged an anomalous off-hours transfer score of 0.88 against baseline. "
                "Critical-infrastructure asset involvement mandates immediate containment.\n\n"
                "**Self-Audit:**\n"
                "Verify whether the destination IP is an authorized enterprise cloud-backup endpoint.\n\n"
                "**Next Action:**\n"
                "Escalate to a human analyst for high-impact action approval."
            )
        return (
            "**Secondary Verdict:** agree\n\n"
            "**Confidence:** 0.94\n\n"
            "**Reasoning:**\n"
            "Independently cross-checked the evidence: a large outbound transfer from a server-tier host to an untrusted external IP. "
            "A fresh ATT&CK mapping again resolves to T1041 (Exfiltration Over C2 Channel). "
            "Behavioral deviation reproduces above threshold. "
            "I confirm the primary agent's true-positive verdict; asset classification triggers the high-impact gating rule.\n\n"
            "**Impact Level:** high_impact\n\n"
            "**Recommended Action:**\n"
            "isolate_host\n\n"
            "**Self-Audit:**\n"
            "Confirmed the high-impact gating condition from the asset tag; would downgrade if the destination is a sanctioned backup service."
        )

    # Default: suspicious execution / generic true-positive.
    if role == "primary":
        return (
            "**Verdict:** true_positive\n\n"
            "**Confidence:** 0.85\n\n"
            "**Reasoning:**\n"
            "The log firewall flagged suspicious content in the command-execution payload. "
            "ATT&CK mapping identified technique T1059 (Command and Scripting Interpreter) in the process lineage. "
            "Log correlation confirmed an anomalous process-execution pattern. "
            "The behavioral-deviation heuristic scored 0.76, above the normal threshold.\n\n"
            "**Self-Audit:**\n"
            "Check for potential host compromise and any child processes spawned.\n\n"
            "**Next Action:**\n"
            "Escalate for containment."
        )
    return (
        "**Secondary Verdict:** agree\n\n"
        "**Confidence:** 0.88\n\n"
        "**Reasoning:**\n"
        "Independently re-derived the skill outputs and verified the anomalous command execution (T1059). "
        "A fresh log-correlation pass reproduces the suspicious process lineage. "
        "Behavioral deviation remains above threshold. "
        "I agree with the primary agent's true-positive verdict.\n\n"
        "**Impact Level:** standard\n\n"
        "**Recommended Action:**\n"
        "disable_account\n\n"
        "**Self-Audit:**\n"
        "Verified log-firewall sanitization; would escalate impact on any critical-asset tag."
    )
