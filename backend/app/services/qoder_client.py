"""Qoder Cloud Agents API client.

Wraps the three core endpoints:
- Create session:  POST /sessions
- Send message:    POST /sessions/{id}/events
- Stream response: GET  /sessions/{id}/events/stream (SSE)
"""

import json
from typing import Any

import requests

from app.core.config import settings


class QoderClientError(Exception):
    """Raised when a Qoder API call fails."""


class QoderClient:
    """Synchronous client for the Qoder Cloud Agents API."""

    def __init__(
        self,
        pat: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self._pat = pat or settings.qoder_pat
        self._base = (api_base or settings.qoder_api_base).rstrip("/")
        if not self._pat:
            raise QoderClientError(
                "QODER_PAT not configured. Set it in your .env file."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._pat}",
                "Content-Type": "application/json",
            }
        )
        # Mount retry adapter for transient connection errors
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry = Retry(total=3, backoff_factor=1,
                      status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    # ── Sessions ──────────────────────────────────────────────────────────

    def create_session(
        self,
        agent_id: str | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new session bound to an agent and environment.

        Returns the full session object including ``id``.
        """
        agent = agent_id or settings.qoder_primary_agent_id
        env = environment_id or settings.qoder_primary_env_id

        if not agent or not env:
            raise QoderClientError(
                "Agent ID and Environment ID are required. "
                "Set QODER_PRIMARY_AGENT_ID and QODER_PRIMARY_ENV_ID in .env"
            )

        resp = self._session.post(
            f"{self._base}/sessions",
            json={"agent": agent, "environment_id": env},
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            raise QoderClientError(
                f"Failed to create session: {resp.status_code} {resp.text}"
            )
        return resp.json()

    # ── Messages ──────────────────────────────────────────────────────────

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        """Send a user message to a session to trigger agent reasoning."""
        payload = {
            "events": [
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": text}],
                }
            ]
        }
        resp = self._session.post(
            f"{self._base}/sessions/{session_id}/events",
            json=payload,
            timeout=30,
        )
        if resp.status_code not in (200, 201, 202):
            raise QoderClientError(
                f"Failed to send message: {resp.status_code} {resp.text}"
            )
        return resp.json()

    # ── Streaming ─────────────────────────────────────────────────────────

    def stream_response(self, session_id: str, timeout: int = 120) -> str:
        """Subscribe to the SSE stream and collect the agent's full text reply.

        Blocks until the agent finishes (or ``timeout`` seconds elapse).
        Returns the concatenated text from all ``agent.message`` events.
        """
        url = f"{self._base}/sessions/{session_id}/events/stream"
        headers = {"Accept": "text/event-stream"}

        collected_text: list[str] = []
        current_event_type: str | None = None
        try:
            with self._session.get(
                url, headers=headers, stream=True, timeout=timeout
            ) as resp:
                if resp.status_code != 200:
                    raise QoderClientError(
                        f"Stream failed: {resp.status_code} {resp.text}"
                    )

                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue

                    # Skip heartbeat lines
                    if raw_line.startswith(": heartbeat"):
                        continue

                    # Track the event type from "event:" lines
                    if raw_line.startswith("event:"):
                        current_event_type = raw_line[len("event:"):].strip()
                        continue

                    # Skip non-data lines (id:, etc.)
                    if not raw_line.startswith("data:"):
                        continue

                    data_str = raw_line[len("data:"):].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Extract text from agent.message events
                    if current_event_type == "agent.message":
                        for block in event.get("content", []):
                            if block.get("type") == "text":
                                collected_text.append(block["text"])

                    # Stop when session goes idle (agent finished)
                    if current_event_type and "status_idle" in current_event_type:
                        break

                    # Also stop on end_turn
                    stop_reason = event.get("stop_reason", {})
                    if stop_reason.get("type") == "end_turn":
                        break

        except requests.exceptions.Timeout:
            raise QoderClientError(
                f"Stream timed out after {timeout}s"
            )

        return "".join(collected_text).strip()

    # ── Convenience ───────────────────────────────────────────────────────

    def triage_alert(self, alert_payload: dict[str, Any]) -> dict[str, Any]:
        """Full investigation flow: retrieve memory → enrich → investigate → parse.

        Runs the complete Phase 7 investigation pipeline:
        1. Retrieve similar past cases (stub — Phase 11)
        2. Run all 4 investigation skills
        3. Build structured prompt with evidence requirements
        4. Send to agent and collect response
        5. Parse the response into structured fields
        6. Classify impact level

        Returns a dict with session_id, agent_response, parsed fields,
        enrichment data, and impact_level.
        """
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

        # 1. Retrieve similar past cases (Phase 11 stub)
        similar_cases = retrieve_similar_cases(alert_type, payload)

        # 2. Run all 4 investigation skills
        otx = enrich_iocs(payload)
        attack = map_attack_techniques(alert_type, payload)
        log_corr = correlate_logs(alert_type, payload)
        deviation = detect_deviation(alert_type, payload)

        enrichment = {
            "otx_enrichment": otx,
            "attack_mapping": attack,
            "log_correlation": log_corr,
            "behavioral_deviation": deviation,
        }

        # 3. Classify impact level (real logic, not LLM)
        impact_level = classify_impact(alert_type, payload)

        # 4. Create session
        session = self.create_session()
        session_id = session.get("id", session.get("session_id", ""))
        if not session_id:
            raise QoderClientError(f"No session ID in response: {session}")

        # 5. Build structured investigation prompt
        prompt = self._build_investigation_prompt(
            alert_payload, alert_type, payload,
            enrichment, similar_cases,
        )

        # 6. Send message and collect response
        self.send_message(session_id, prompt)
        response_text = self.stream_response(session_id)

        # 7. Parse the agent's response into structured fields
        parsed = parse_agent_response(response_text)

        return {
            "session_id": session_id,
            "agent_response": response_text,
            "parsed": parsed,
            "enrichment": enrichment,
            "impact_level": impact_level,
            "similar_cases": similar_cases,
        }

    def _build_investigation_prompt(
        self,
        alert_payload: dict[str, Any],
        alert_type: str,
        payload: dict[str, Any],
        enrichment: dict[str, Any],
        similar_cases: list[dict[str, Any]],
    ) -> str:
        """Build the structured investigation prompt.

        The prompt requires the agent to:
        - Cite specific skill outputs as evidence
        - Produce a clear verdict and confidence
        - Self-audit what could change the verdict
        """
        otx = enrichment["otx_enrichment"]
        attack = enrichment["attack_mapping"]
        log_corr = enrichment["log_correlation"]
        deviation = enrichment["behavioral_deviation"]

        # Memory context section
        if similar_cases:
            memory_section = (
                f"## Similar Past Cases ({len(similar_cases)} found)\n"
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
            "specific outputs from the skills above. For example:\n"
            "- 'OTX enrichment shows IP X has reputation score Y...'\n"
            "- 'ATT&CK mapping identified technique T1110.001 based on...'\n"
            "- 'Log correlation detected a sequence of...'\n"
            "- 'Behavioral deviation flagged off-hours activity with score...'\n\n"
            "**Self-Audit:**\n"
            "State what evidence could change this verdict, and any gaps "
            "in the current investigation. Be honest about uncertainty.\n\n"
            "**Next Action:**\n"
            "Recommend what should happen next (close, escalate, investigate further)."
        )

        return prompt


# ── Module-level convenience ──────────────────────────────────────────────

_client: QoderClient | None = None


def get_qoder_client() -> QoderClient:
    """Return a singleton QoderClient instance."""
    global _client
    if _client is None:
        _client = QoderClient()
    return _client
