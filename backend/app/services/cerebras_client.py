"""Cerebras LLM client — Secondary Deep Investigation Agent.

Provider 2 of the final three-provider architecture:

- **Groq** → Primary Alert Triage Agent (``groq_client.py``)
- **Cerebras** → Secondary Deep Investigation Agent (this module)
- **Cloudflare Workers AI** → live alert generator (``cloudflare_client.py``)

Cerebras exposes an OpenAI-compatible Chat Completions API with SSE streaming,
so this client has the *same interface shape* as ``groq_client.py``: virtual
sessions, token-by-token ``{"type": "delta", "text": ...}`` streaming, and the
same ``triage_alert`` / ``reinvestigate_alert`` return dicts.  Verdict,
confidence, reasoning and self-audit are parsed identically because the system
prompts, prompt builders and fallback text are shared from
:mod:`app.services.agent_prompts`.

All network calls go through :func:`app.services.provider_common.post_with_backoff`
— rate-limits / transient errors are retried with exponential backoff (1s, 2s,
4s) before falling back.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator
from uuid import uuid4

import requests

from app.core.config import settings
from app.services.agent_prompts import (
    build_investigation_prompt,
    build_reinvestigation_prompt,
    fallback_agent_text,
    system_prompt_for_role,
)
from app.services.provider_common import post_with_backoff

logger = logging.getLogger(__name__)

# Cerebras OpenAI-compatible API base.
_CEREBRAS_API_BASE = "https://api.cerebras.ai/v1"


class CerebrasClientError(Exception):
    """Raised when a Cerebras API call fails."""


class CerebrasClient:
    """Synchronous Cerebras client for the Secondary Deep Investigation Agent."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.cerebras_api_key
        self._model = model or settings.cerebras_model or "gpt-oss-120b"
        if not self._api_key:
            raise CerebrasClientError(
                "CEREBRAS_API_KEY not configured. Set CEREBRAS_API_KEY in your .env file."
            )

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
        )
        self.provider_name = "cerebras"
        self._virtual_sessions: dict[str, dict[str, Any]] = {}

    # ── Sessions (virtual facade) ─────────────────────────────────────────────

    def create_session(
        self,
        agent_id: str | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a virtual session and return ``{"id": ...}``.

        Cerebras is the Secondary Agent, so an unspecified role defaults to
        ``"secondary"`` (the pipeline always passes ``agent_id="secondary"``
        explicitly, but this keeps the default sensible).
        """
        role = (
            "primary"
            if (agent_id == "primary" or environment_id == "primary")
            else "secondary"
        )
        session_id = f"cerebras-session-{uuid4().hex[:12]}"
        session_obj = {
            "id": session_id,
            "session_id": session_id,
            "agent_role": role,
            "prompt": None,
        }
        self._virtual_sessions[session_id] = session_obj
        logger.info("Created Cerebras virtual session %s for role=%s", session_id, role)
        return session_obj

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        """Store the user prompt for a virtual session."""
        if session_id not in self._virtual_sessions:
            self._virtual_sessions[session_id] = {
                "id": session_id,
                "session_id": session_id,
                "agent_role": "secondary",
                "prompt": text,
            }
        else:
            self._virtual_sessions[session_id]["prompt"] = text
        return {"status": "ok", "session_id": session_id}

    # ── Streaming (SSE) ───────────────────────────────────────────────────────

    def stream_session_events(
        self, session_id: str, timeout: int = 120
    ) -> Iterator[dict[str, Any]]:
        """Call Cerebras Chat Completions with ``stream=True`` and yield deltas.

        Yields ``{"type": "delta", "text": token}`` for each streamed chunk.  On
        a permanent rejection (e.g. HTTP 402 — no inference quota) or an
        exhausted retry budget, falls back to the deterministic report generator
        so the investigation pipeline never dies mid-demo.
        """
        sess_data = self._virtual_sessions.get(session_id)
        if not sess_data or not sess_data.get("prompt"):
            raise CerebrasClientError(f"No prompt found for Cerebras session {session_id}")

        role = sess_data.get("agent_role", "secondary")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt_for_role(role)},
                {"role": "user", "content": sess_data["prompt"]},
            ],
            "temperature": 0.2,
            "stream": True,
        }
        url = f"{_CEREBRAS_API_BASE}/chat/completions"

        try:
            resp = post_with_backoff(
                self._session, url, provider="cerebras", json=payload, stream=True, timeout=timeout
            )
        except requests.RequestException as exc:
            logger.warning(
                "Cerebras connection failed after retries (%s) — using deterministic fallback.", exc
            )
            yield from self._generate_fallback_stream(session_id)
            return

        if resp.status_code != 200:
            logger.warning(
                "Cerebras API returned HTTP %s (%s) — using deterministic fallback report.",
                resp.status_code,
                resp.text[:200],
            )
            resp.close()
            yield from self._generate_fallback_stream(session_id)
            return

        yielded_any = False
        try:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                content_piece = choices[0].get("delta", {}).get("content", "")
                if content_piece:
                    yielded_any = True
                    yield {"type": "delta", "text": content_piece}
        except requests.RequestException as exc:
            logger.warning("Cerebras stream interrupted (%s).", exc)
        finally:
            resp.close()

        if not yielded_any:
            logger.warning(
                "Cerebras returned an empty stream — using deterministic fallback report."
            )
            yield from self._generate_fallback_stream(session_id)

    def _generate_fallback_stream(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Stream a deterministic, evidence-styled report word-by-word.

        Used only when Cerebras rejects the call permanently (e.g. 402 quota) or
        the stream is empty.  Shared text lives in
        :mod:`app.services.agent_prompts` so the fallback is identical in shape
        to a live report and parses the same way.
        """
        sess_data = self._virtual_sessions.get(session_id)
        if not sess_data or not sess_data.get("prompt"):
            raise CerebrasClientError(
                f"No prompt found for Cerebras fallback session {session_id}"
            )

        role = str(sess_data.get("agent_role", "secondary"))
        logger.warning(
            "Cerebras fallback engaged for session %s (role=%s) — deterministic report, NOT live model output.",
            session_id,
            role,
        )
        text = fallback_agent_text(role, str(sess_data["prompt"]))
        words = text.split(" ")
        for i, word in enumerate(words):
            time.sleep(0.03)
            yield {"type": "delta", "text": word + (" " if i < len(words) - 1 else "")}

    def stream_response(self, session_id: str, timeout: int = 120) -> str:
        """Collect and return the full text response from the Cerebras stream."""
        parts: list[str] = []
        for stream_event in self.stream_session_events(session_id, timeout):
            if stream_event["type"] == "delta":
                parts.append(stream_event["text"])
        return "".join(parts).strip()

    # ── High-level investigation pipelines ────────────────────────────────────

    def triage_alert(self, alert_payload: dict[str, Any]) -> dict[str, Any]:
        """Run a Primary-style triage via Cerebras (interface parity)."""
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
            "Cerebras Primary Triage for alert %s complete: verdict=%s, conf=%.2f",
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
            "agent_provider": "cerebras",
        }

    def reinvestigate_alert(
        self,
        alert_payload: dict[str, Any],
        primary_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the Secondary Agent's independent re-investigation via Cerebras."""
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
            "Cerebras Secondary Re-investigation for alert %s complete: sec_verdict=%s",
            alert_payload.get("source_alert_id"),
            parsed.get("secondary_verdict"),
        )
        return {
            "session_id": session_id,
            "agent_response": response_text,
            "parsed": parsed,
            "enrichment": enrichment,
            "similar_cases": similar_cases,
            "agent_provider": "cerebras",
        }

    # ── Prompt builders (shared, provider-agnostic) ───────────────────────────

    def _build_investigation_prompt(
        self,
        alert_payload: dict[str, Any],
        alert_type: str,
        payload: dict[str, Any],
        enrichment: dict[str, Any],
        similar_cases: list[dict[str, Any]],
    ) -> str:
        return build_investigation_prompt(
            alert_payload, alert_type, payload, enrichment, similar_cases
        )

    def _build_reinvestigation_prompt(
        self,
        alert_payload: dict[str, Any],
        alert_type: str,
        payload: dict[str, Any],
        enrichment: dict[str, Any],
        primary_result: dict[str, Any],
        similar_cases: list[dict[str, Any]] | None = None,
    ) -> str:
        return build_reinvestigation_prompt(
            alert_payload, alert_type, payload, enrichment, primary_result, similar_cases
        )


# Singleton instance helper
_cerebras_client: CerebrasClient | None = None


def get_cerebras_client() -> CerebrasClient:
    """Return a singleton CerebrasClient instance."""
    global _cerebras_client
    if _cerebras_client is None:
        _cerebras_client = CerebrasClient()
    return _cerebras_client
