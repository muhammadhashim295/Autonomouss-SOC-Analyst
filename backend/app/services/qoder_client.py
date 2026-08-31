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
        """Full triage flow: enrich → create session → send alert → collect response.

        Runs all 4 investigation skills and includes results in the agent prompt.
        Returns ``{"session_id": ..., "agent_response": ..., "enrichment": ...}``.
        """
        from app.services.skills import (
            correlate_logs,
            detect_deviation,
            enrich_iocs,
            map_attack_techniques,
        )

        alert_type = alert_payload.get("alert_type", "unknown")
        payload = alert_payload.get("raw_payload", {})

        # 1. Run all 4 investigation skills
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

        # 2. Create session
        session = self.create_session()
        session_id = session.get("id", session.get("session_id", ""))
        if not session_id:
            raise QoderClientError(f"No session ID in response: {session}")

        # 3. Build the investigation prompt with enrichment data
        prompt = (
            "Investigate the following security alert and produce a full "
            "investigation report following your required output format.\n\n"
            "## Alert Data\n"
            f"**Alert ID:** {alert_payload.get('source_alert_id', 'unknown')}\n"
            f"**Alert Type:** {alert_type}\n"
            f"**Raw Payload:**\n```json\n"
            f"{json.dumps(payload, indent=2)}\n```\n\n"
            "## Pre-computed Investigation Skills Results\n"
            "Use these as evidence for your investigation report.\n\n"
            f"### OTX IOC Enrichment\n{json.dumps(otx, indent=2)}\n\n"
            f"### ATT&CK Mapping\n{json.dumps(attack, indent=2)}\n\n"
            f"### Log Correlation\n{json.dumps(log_corr, indent=2)}\n\n"
            f"### Behavioral Deviation\n{json.dumps(deviation, indent=2)}\n\n"
            "Now produce your full investigation report using the format in your instructions."
        )

        # 4. Send message
        self.send_message(session_id, prompt)

        # 5. Collect response
        response_text = self.stream_response(session_id)

        return {
            "session_id": session_id,
            "agent_response": response_text,
            "enrichment": enrichment,
        }


# ── Module-level convenience ──────────────────────────────────────────────

_client: QoderClient | None = None


def get_qoder_client() -> QoderClient:
    """Return a singleton QoderClient instance."""
    global _client
    if _client is None:
        _client = QoderClient()
    return _client
