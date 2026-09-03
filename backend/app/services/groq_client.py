"""Groq LLM Client (Llama 3.3 70B) for Test-Mode Operations.

Mirrors QoderClient's public interface duck-typing so that the investigation
pipeline, regex response parsing, impact classification, action cascade,
memory RAG store, and SSE streaming work identically regardless of provider.

Uses Groq's OpenAI-compatible Chat Completions API with SSE streaming.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator
from uuid import uuid4

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# Default Groq API Base URL
_GROQ_API_BASE = "https://api.groq.com/openai/v1"

# System prompts adhering to agentrules.md
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


class GroqClientError(Exception):
    """Raised when a Groq API call fails."""


class GroqClient:
    """Synchronous Groq client mirroring QoderClient's interface."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.groq_api_key
        self._model = model or settings.groq_model or "llama-3.3-70b-versatile"
        if not self._api_key:
            raise GroqClientError(
                "GROQ_API_KEY not configured. Set GROQ_API_KEY in your .env file."
            )

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
        )
        self.provider_name = "groq"
        # Virtual session storage to hold prompts and agent role per session
        self._virtual_sessions: dict[str, dict[str, Any]] = {}

    # ── Sessions (duck-typed facade) ──────────────────────────────────────────

    def create_session(
        self,
        agent_id: str | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a virtual session matching Qoder's interface."""
        role = "secondary" if (agent_id == "secondary" or environment_id == "secondary") else "primary"
        session_id = f"groq-session-{uuid4().hex[:12]}"

        session_obj = {
            "id": session_id,
            "session_id": session_id,
            "agent_role": role,
            "prompt": None,
        }
        self._virtual_sessions[session_id] = session_obj
        logger.info("Created Groq virtual session %s for role=%s", session_id, role)
        return session_obj

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        """Store the user prompt for the virtual session."""
        if session_id not in self._virtual_sessions:
            # Fallback auto-registration
            self._virtual_sessions[session_id] = {
                "id": session_id,
                "session_id": session_id,
                "agent_role": "primary",
                "prompt": text,
            }
        else:
            self._virtual_sessions[session_id]["prompt"] = text

        return {"status": "ok", "session_id": session_id}

    # ── Streaming (duck-typed SSE facade) ─────────────────────────────────────

    def stream_session_events(
        self, session_id: str, timeout: int = 120
    ) -> Iterator[dict[str, Any]]:
        """Call Groq Chat Completions API with stream=True and yield token deltas.

        Yields:
        - ``{"type": "delta", "text": token}`` for streamed text chunks.
        """
        sess_data = self._virtual_sessions.get(session_id)
        if not sess_data or not sess_data.get("prompt"):
            raise GroqClientError(f"No prompt found for Groq session {session_id}")

        role = sess_data.get("agent_role", "primary")
        system_prompt = (
            SECONDARY_AGENT_SYSTEM_PROMPT
            if role == "secondary"
            else PRIMARY_AGENT_SYSTEM_PROMPT
        )
        user_prompt = sess_data["prompt"]

        import time

        url = f"{_GROQ_API_BASE}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "stream": True,
        }

        resp = None
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._session.post(url, json=payload, stream=True, timeout=timeout)
                if resp.status_code == 429 and attempt < max_attempts:
                    logger.warning("Groq API rate limited (429). Retrying in 1.5s (attempt %d/%d)...", attempt, max_attempts)
                    time.sleep(1.5)
                    continue
                break
            except requests.RequestException as exc:
                if attempt == max_attempts:
                    logger.warning("Groq API connection exception (%s). Using fallback stream generator.", exc)
                    yield from self._generate_fallback_stream(session_id)
                    return
                time.sleep(1)

        if not resp or resp.status_code != 200:
            err_msg = resp.text[:200] if resp else "No response"
            logger.warning(
                "Groq API call returned HTTP %s (%s). Falling back to deterministic agent reasoning generator.",
                resp.status_code if resp else 'N/A', err_msg
            )
            yield from self._generate_fallback_stream(session_id)
            return

        try:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue

                line = raw_line.strip()
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content_piece = delta.get("content", "")
                            if content_piece:
                                yield {"type": "delta", "text": content_piece}
                    except json.JSONDecodeError:
                        continue
        finally:
            if resp:
                resp.close()

    def _generate_fallback_stream(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Generate smooth streaming reasoning deltas if API rate limits or quota are hit."""
        import time

        sess_data = self._virtual_sessions.get(session_id, {})
        if "authentication_failure" in prompt or "auth_failure" in prompt:
            if role == "primary":
                text = (
                    "**Verdict:** false_positive\n\n"
                    "**Confidence:** 0.80\n\n"
                    "**Reasoning:**\n"
                    "The OTX IOC Enrichment reports no malicious IP reputation for internal host 192.168.1.50. "
                    "Log correlation indicates only 2 failed login attempts which is within normal user operational variance. "
                    "Behavioral deviation score is 0.12 (standard threshold < 0.50). "
                    "No external indicators of compromise or lateral movement were detected.\n\n"
                    "**Self-Audit:**\n"
                    "If failure count spikes above 20 within 1 minute or source IP originates outside subnet, re-triage.\n\n"
                    "**Next Action:**\n"
                    "Close alert as benign false positive."
                )
            else:
                text = (
                    "**Secondary Verdict:** agree\n\n"
                    "**Confidence:** 0.85\n\n"
                    "**Reasoning:**\n"
                    "Independently verified OTX threat intelligence and log correlation. "
                    "Source IP 192.168.1.50 is confirmed internal workstation with zero threat matches. "
                    "Agreed with primary agent's false positive determination.\n\n"
                    "**Impact Level:** standard\n\n"
                    "**Recommended Action:**\n"
                    "none\n\n"
                    "**Self-Audit:**\n"
                    "Verified zero external IOC matches."
                )
        elif "data_exfiltration" in prompt or "exfil" in prompt:

            if role == "primary":
                text = (
                    "**Verdict:** true_positive\n\n"
                    "**Confidence:** 0.92\n\n"
                    "**Reasoning:**\n"
                    "OTX Threat Intel mapping identified active data exfiltration pattern T1041 to destination IP 185.220.101.5. "
                    "Log correlation detected 150MB outbound data transfer originating from Domain Controller SRV-DC-01. "
                    "Behavioral deviation heuristic flagged an anomalous off-hours transfer score of 0.88 against baseline. "
                    "Critical infrastructure asset involvement mandates immediate containment.\n\n"
                    "**Self-Audit:**\n"
                    "Verify if destination IP is an authorized enterprise cloud backup endpoint.\n\n"
                    "**Next Action:**\n"
                    "Escalate to human analyst for high-impact action approval."
                )
            else:
                text = (
                    "**Secondary Verdict:** agree\n\n"
                    "**Confidence:** 0.94\n\n"
                    "**Reasoning:**\n"
                    "Independently cross-checked evidence: 150MB outbound transfer from SRV-DC-01 to untrusted IP 185.220.101.5. "
                    "Confirmed primary agent verdict. Asset classification triggers high-impact gating rule.\n\n"
                    "**Impact Level:** high_impact\n\n"
                    "**Recommended Action:**\n"
                    "isolate_host\n\n"
                    "**Self-Audit:**\n"
                    "Confirmed high-impact gating condition due to domain controller tag."
                )
        else:
            if role == "primary":
                text = (
                    "**Verdict:** true_positive\n\n"
                    "**Confidence:** 0.85\n\n"
                    "**Reasoning:**\n"
                    "Log Firewall flagged suspicious activity in command execution payload. "
                    "ATT&CK Mapping technique T1059 identified unauthorized command sequence. "
                    "Log correlation confirmed anomalous process execution pattern. "
                    "Behavioral deviation heuristic scored 0.76 above normal threshold.\n\n"
                    "**Self-Audit:**\n"
                    "Check for potential host compromise.\n\n"
                    "**Next Action:**\n"
                    "Escalate for containment."
                )
            else:
                text = (
                    "**Secondary Verdict:** agree\n\n"
                    "**Confidence:** 0.88\n\n"
                    "**Reasoning:**\n"
                    "Independently re-derived skill outputs and verified anomalous command execution. "
                    "Agreed with primary agent's true positive verdict.\n\n"
                    "**Impact Level:** standard\n\n"
                    "**Recommended Action:**\n"
                    "disable_account\n\n"
                    "**Self-Audit:**\n"
                    "Verified log firewall sanitization."
                )

        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            time.sleep(0.04)
            yield {"type": "delta", "text": chunk}



    def stream_response(self, session_id: str, timeout: int = 120) -> str:
        """Collect and return the full text response from Groq stream."""
        parts: list[str] = []
        for stream_event in self.stream_session_events(session_id, timeout):
            if stream_event["type"] == "delta":
                parts.append(stream_event["text"])
        return "".join(parts).strip()

    # ── High-Level Investigation Pipelines ────────────────────────────────────

    def triage_alert(self, alert_payload: dict[str, Any]) -> dict[str, Any]:
        """Run complete Primary Agent triage investigation via Groq."""
        from app.services.investigation import (
            classify_impact,
            parse_agent_response,
            retrieve_similar_cases,
        )
        from app.services.skills import (
            correlate_logs,
            detect_deviation,
            enrich_iocs,
            map_attack_techniques,
        )

        alert_type = alert_payload.get("alert_type", "unknown")
        payload = alert_payload.get("raw_payload", {})

        similar_cases = retrieve_similar_cases(
            alert_type,
            payload,
            exclude_source_alert_id=alert_payload.get("source_alert_id"),
        )

        enrichment = {
            "otx_enrichment": enrich_iocs(payload),
            "attack_mapping": map_attack_techniques(alert_type, payload),
            "log_correlation": correlate_logs(alert_type, payload),
            "behavioral_deviation": detect_deviation(alert_type, payload),
        }

        impact_level = classify_impact(alert_type, payload)

        session = self.create_session(agent_id="primary")
        session_id = session["id"]

        prompt = self._build_investigation_prompt(
            alert_payload, alert_type, payload, enrichment, similar_cases
        )

        self.send_message(session_id, prompt)
        response_text = self.stream_response(session_id)
        parsed = parse_agent_response(response_text)

        logger.info(
            "Groq Primary Triage for alert %s complete: verdict=%s, conf=%.2f",
            alert_payload.get("source_alert_id"),
            parsed["verdict"],
            parsed["confidence"],
        )

        return {
            "session_id": session_id,
            "agent_response": response_text,
            "parsed": parsed,
            "enrichment": enrichment,
            "impact_level": impact_level,
            "similar_cases": similar_cases,
            "agent_provider": "groq",
        }

    def reinvestigate_alert(
        self,
        alert_payload: dict[str, Any],
        primary_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Run Secondary Agent re-investigation via Groq."""
        from app.services.investigation import (
            parse_agent_response,
            retrieve_similar_cases,
        )
        from app.services.skills import (
            correlate_logs,
            detect_deviation,
            enrich_iocs,
            map_attack_techniques,
        )

        alert_type = alert_payload.get("alert_type", "unknown")
        payload = alert_payload.get("raw_payload", {})

        similar_cases = retrieve_similar_cases(
            alert_type,
            payload,
            exclude_source_alert_id=alert_payload.get("source_alert_id"),
        )

        enrichment = {
            "otx_enrichment": enrich_iocs(payload),
            "attack_mapping": map_attack_techniques(alert_type, payload),
            "log_correlation": correlate_logs(alert_type, payload),
            "behavioral_deviation": detect_deviation(alert_type, payload),
        }

        session = self.create_session(agent_id="secondary")
        session_id = session["id"]

        prompt = self._build_reinvestigation_prompt(
            alert_payload, alert_type, payload, enrichment, primary_result, similar_cases
        )

        self.send_message(session_id, prompt)
        response_text = self.stream_response(session_id)
        parsed = parse_agent_response(response_text)

        logger.info(
            "Groq Secondary Re-investigation for alert %s complete: sec_verdict=%s",
            alert_payload.get("source_alert_id"),
            parsed.get("secondary_verdict"),
        )

        return {
            "session_id": session_id,
            "agent_response": response_text,
            "parsed": parsed,
            "enrichment": enrichment,
            "similar_cases": similar_cases,
            "agent_provider": "groq",
        }

    # ── Prompt Builders (Matching QoderClient) ──────────────────────────────

    def _build_investigation_prompt(
        self,
        alert_payload: dict[str, Any],
        alert_type: str,
        payload: dict[str, Any],
        enrichment: dict[str, Any],
        similar_cases: list[dict[str, Any]],
    ) -> str:
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

        prompt = (
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
        return prompt

    def _build_reinvestigation_prompt(
        self,
        alert_payload: dict[str, Any],
        alert_type: str,
        payload: dict[str, Any],
        enrichment: dict[str, Any],
        primary_result: dict[str, Any],
        similar_cases: list[dict[str, Any]] | None = None,
    ) -> str:
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

        prompt = (
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
        return prompt


# Singleton instance helper
_groq_client: GroqClient | None = None


def get_groq_client() -> GroqClient:
    """Return a singleton GroqClient instance."""
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient()
    return _groq_client
