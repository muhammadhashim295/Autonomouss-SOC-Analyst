"""Agent Provider Factory and Execution Safeguard.

Provides a unified factory to resolve the active agent provider
(`qoder` vs `groq`) once per investigation request.

Enforces CRITICAL SAFEGUARDS:
- Providers are strictly mutually exclusive (if/else dispatch).
- Zero fallback mid-flow (a Qoder failure never consumes Groq credits, and vice versa).
- Provider choice is logged explicitly per investigation run.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings
from app.services.groq_client import GroqClient, get_groq_client
from app.services.qoder_client import QoderClient, get_qoder_client

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentClientProtocol(Protocol):
    """Duck-typed protocol enforced for both QoderClient and GroqClient."""

    provider_name: str

    def triage_alert(self, alert_payload: dict[str, Any]) -> dict[str, Any]: ...

    def reinvestigate_alert(
        self, alert_payload: dict[str, Any], primary_result: dict[str, Any]
    ) -> dict[str, Any]: ...

    def create_session(
        self, agent_id: str | None = None, environment_id: str | None = None
    ) -> dict[str, Any]: ...

    def send_message(self, session_id: str, text: str) -> dict[str, Any]: ...

    def stream_session_events(
        self, session_id: str, timeout: int = 120
    ) -> Any: ...

    def stream_response(self, session_id: str, timeout: int = 120) -> str: ...


def get_agent_client(provider: str | None = None) -> QoderClient | GroqClient:
    """Return the agent client instance according to the resolved provider.

    Parameters
    ----------
    provider : str | None
        Explicit provider name ("qoder" or "groq"). If None, reads from
        settings.agent_provider (which loads AGENT_PROVIDER from .env).

    Returns
    -------
    QoderClient | GroqClient
        The active client instance for this investigation request.
    """
    resolved_provider = (provider or settings.agent_provider or "qoder").lower().strip()

    if resolved_provider == "groq":
        logger.info(
            "AGENT_PROVIDER resolved to 'groq' — dispatching to GroqClient (Llama 3.3 70B). Zero Qoder credits will be used."
        )
        return get_groq_client()
    elif resolved_provider == "qoder":
        logger.info(
            "AGENT_PROVIDER resolved to 'qoder' — dispatching to QoderClient (Qoder Cloud Agents). Zero Groq API calls will be made."
        )
        return get_qoder_client()
    else:
        raise ValueError(
            f"Invalid AGENT_PROVIDER '{resolved_provider}'. Must be 'qoder' or 'groq'."
        )
