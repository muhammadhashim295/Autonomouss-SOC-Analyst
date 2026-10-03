"""Groq LLM client — Powers both Primary and Secondary SOC Agents.

Provider 1 of the 2-provider architecture:
- **Groq** → Primary Alert Triage Agent AND Secondary Deep Investigation Agent
- **Cloudflare Workers AI** → Live alert generator (``cloudflare_client.py``)

Groq exposes an OpenAI-compatible Chat Completions API with SSE streaming, so
this client streams token-by-token and emits ``{"type": "delta", "text": ...}``
events that the pipeline relays as ``agent_delta``. Agent behaviour (system
prompts, structured prompt builders, deterministic fallback text) lives in
:mod:`app.services.agent_prompts` per role ('primary' vs 'secondary').

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

# Groq OpenAI-compatible API base.
_GROQ_API_BASE = "https://api.groq.com/openai/v1"


class GroqClientError(Exception):
    """Raised when a Groq API call fails."""


class GroqClient:
    """Synchronous Groq client for the Primary Alert Triage Agent."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.groq_api_key
        self._model = model or settings.groq_model or "openai/gpt-oss-120b"
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
        # Virtual-session storage: holds the prompt + agent role per session so
        # create_session/send_message/stream_session_events stay decoupled.
        self._virtual_sessions: dict[str, dict[str, Any]] = {}

    # ── Sessions (virtual facade) ─────────────────────────────────────────────

    def create_session(
        self,
        agent_id: str | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a virtual session and return ``{"id": ...}``."""
        role = (
            "secondary"
            if (agent_id == "secondary" or environment_id == "secondary")
            else "primary"
        )
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
        """Store the user prompt for a virtual session."""
        if session_id not in self._virtual_sessions:
            self._virtual_sessions[session_id] = {
                "id": session_id,
                "session_id": session_id,
                "agent_role": "primary",
                "prompt": text,
            }
        else:
            self._virtual_sessions[session_id]["prompt"] = text
        return {"status": "ok", "session_id": session_id}

    # ── Streaming (SSE) ───────────────────────────────────────────────────────

    def stream_session_events(
        self, session_id: str, timeout: int = 120
    ) -> Iterator[dict[str, Any]]:
        """Call Groq Chat Completions with ``stream=True`` and yield token deltas.

        Yields ``{"type": "delta", "text": token}`` for each streamed chunk.
        On a permanent rejection (no quota / org-blocked model / bad key) or an
        exhausted retry budget, falls back to the deterministic report generator
        so the investigation pipeline never dies mid-demo.
        """
        sess_data = self._virtual_sessions.get(session_id)
        if not sess_data or not sess_data.get("prompt"):
            raise GroqClientError(f"No prompt found for Groq session {session_id}")

        role = sess_data.get("agent_role", "primary")
        selected_model = (
            settings.groq_secondary_model
            if (role == "secondary" and settings.groq_secondary_model)
            else self._model
        )
        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt_for_role(role)},
                {"role": "user", "content": sess_data["prompt"]},
            ],
            "temperature": 0.2,
            "max_tokens": settings.groq_max_tokens,
            "stream": True,
        }
        url = f"{_GROQ_API_BASE}/chat/completions"

        try:
            resp = post_with_backoff(
                self._session, url, provider="groq", json=payload, stream=True, timeout=timeout
            )
        except requests.RequestException as exc:
            logger.warning(
                "Groq connection failed after retries (%s) — using deterministic fallback.", exc
            )
            yield from self._generate_fallback_stream(session_id)
            return

        # Groq streams ``text/event-stream`` with no charset in the header, so
        # requests defaults ``resp.encoding`` to ISO-8859-1 (per the original
        # HTTP spec).  ``iter_lines(decode_unicode=True)`` then decodes UTF-8
        # bytes as Latin-1, baking mojibake (smart quotes, bullets, dashes ->
        # "a-€-¢") into the Python string before it is ever relayed.  Pin the
        # decoding to UTF-8 explicitly — this is the root-cause fix.
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            logger.warning(
                "Groq API returned HTTP %s (%s) — using deterministic fallback report.",
                resp.status_code,
                resp.text[:200],
            )
            resp.close()
            yield from self._generate_fallback_stream(session_id)
            return

        yielded_any = False
        finish_reason: str | None = None
        collected_chars = 0
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
                # Track why the stream ended so a truncated report is visible
                # rather than silently mistaken for a clean handoff.
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
                # gpt-oss reasoning models stream reasoning separately; only the
                # final answer (``content``) forms the structured report we parse.
                content_piece = choices[0].get("delta", {}).get("content", "")
                if content_piece:
                    yielded_any = True
                    collected_chars += len(content_piece)
                    yield {"type": "delta", "text": content_piece}
        except requests.RequestException as exc:
            logger.error(
                "Groq stream interrupted mid-response for session %s (role=%s): %s — "
                "collected %d chars before the drop.",
                session_id, role, exc, collected_chars,
            )
        except Exception as exc:  # noqa: BLE001 — never let a decode/parse blip die silently
            logger.exception(
                "Unexpected error while streaming Groq response for session %s: %s",
                session_id, exc,
            )
        finally:
            resp.close()

        if finish_reason == "length":
            logger.warning(
                "Groq report for session %s (role=%s) was TRUNCATED at the token cap "
                "(max_tokens=%s) — reasoning may end mid-sentence. Raise groq_max_tokens "
                "if this persists.",
                session_id, role, settings.groq_max_tokens,
            )

        if not yielded_any:
            logger.warning("Groq returned an empty stream — using deterministic fallback report.")
            yield from self._generate_fallback_stream(session_id)

    def _generate_fallback_stream(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Stream a deterministic, evidence-styled report word-by-word.

        Used only when Groq rejects the call permanently or the stream is empty.
        Shared text lives in :mod:`app.services.agent_prompts` so the fallback is
        identical in shape to a live report and parses the same way.
        """
        sess_data = self._virtual_sessions.get(session_id)
        if not sess_data or not sess_data.get("prompt"):
            raise GroqClientError(f"No prompt found for Groq fallback session {session_id}")

        role = str(sess_data.get("agent_role", "primary"))
        logger.warning(
            "Groq fallback engaged for session %s (role=%s) — deterministic report, NOT live model output.",
            session_id,
            role,
        )
        text = fallback_agent_text(role, str(sess_data["prompt"]))
        words = text.split(" ")
        for i, word in enumerate(words):
            time.sleep(0.03)
            yield {"type": "delta", "text": word + (" " if i < len(words) - 1 else "")}

    def stream_response(self, session_id: str, timeout: int = 120) -> str:
        """Collect and return the full text response from the Groq stream."""
        parts: list[str] = []
        for stream_event in self.stream_session_events(session_id, timeout):
            if stream_event["type"] == "delta":
                parts.append(stream_event["text"])
        return "".join(parts).strip()

    # ── High-level investigation pipelines ────────────────────────────────────

    def triage_alert(self, alert_payload: dict[str, Any]) -> dict[str, Any]:
        """Run the complete Primary Agent triage investigation via Groq."""
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
        """Run a Secondary Agent re-investigation via Groq (interface parity)."""
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
_groq_client: GroqClient | None = None


def get_groq_client() -> GroqClient:
    """Return a singleton GroqClient instance."""
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient()
    return _groq_client
