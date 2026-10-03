"""Shared retry-with-backoff helper for ALL provider network calls.

Every outbound call to the two providers (Groq — Primary & Secondary Agents,
Cloudflare Workers AI — live alert generator) is routed through
:func:`post_with_backoff` so that a rate-limit (HTTP 429) or transient
server/network error is retried with exponential backoff (1s, 2s, 4s — max 3 retries).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# HTTP statuses that are worth retrying: rate limits and transient
# server-side / network conditions. 403 (org blocked), 401 (bad key),
# 404 (unknown model), 400 (bad request) are deliberately excluded —
# backoff cannot fix a permanent rejection.
TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

# A 402/429 whose body reports a spent allocation window (e.g. Cloudflare's
# "daily free allocation of 10,000 neurons") is NOT a momentary rate limit:
# waiting seconds cannot fix it, only the next quota window.  Callers use
# this to fail fast and degrade instead of burning the whole retry budget.
_HARD_QUOTA_MARKERS = (
    "daily free allocation",
    "used up your daily",
    "daily allowance",
    "daily token limit",
    "quota exhausted",
    "quota exceeded",
)


def is_transient_status(status_code: int) -> bool:
    """Whether an HTTP status code represents a retryable condition."""
    return status_code in TRANSIENT_STATUS_CODES


def is_hard_quota_response(status_code: int, text: str = "") -> bool:
    """Whether a response reports a spent quota window (not retryable by backoff)."""
    if status_code not in (402, 429):
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _HARD_QUOTA_MARKERS)


def post_with_backoff(
    session: requests.Session,
    url: str,
    *,
    provider: str,
    json: Optional[dict[str, Any]] = None,
    stream: bool = False,
    timeout: int = 120,
    max_retries: Optional[int] = None,
    base_seconds: Optional[float] = None,
) -> requests.Response:
    """POST ``json`` to ``url`` with exponential backoff on transient errors.

    Parameters
    ----------
    session : requests.Session
        Pre-authenticated session (Authorization header already set).
    url : str
        Full endpoint URL.
    provider : str
        Provider label used in log lines ("groq" | "cloudflare").
    stream : bool
        Whether to open the response for streaming (SSE) consumption.
    max_retries : int | None
        Retry budget; defaults to ``settings.provider_max_retries`` (3).
    base_seconds : float | None
        First backoff delay; defaults to
        ``settings.provider_backoff_base_seconds`` (1.0).  Delays are
        ``base * 2**attempt`` -> 1s, 2s, 4s.

    Returns
    -------
    requests.Response
        The final response (200 on success, or the last non-transient /
        last-transient-after-exhaustion response so the caller can log
        the exact status and body).

    Raises
    ------
    requests.RequestException
        Only when a connection-level error persists past the retry budget.
    """
    retries = settings.provider_max_retries if max_retries is None else max_retries
    base = settings.provider_backoff_base_seconds if base_seconds is None else base_seconds

    last_response: Optional[requests.Response] = None

    # attempt 0 is the initial call; attempts 1..retries are the retries.
    for attempt in range(retries + 1):
        try:
            response = session.post(url, json=json, stream=stream, timeout=timeout)
        except requests.RequestException as exc:
            if attempt < retries:
                delay = base * (2 ** attempt)
                logger.warning(
                    "[%s] connection error on POST %s (%s) — retry %d/%d in %.1fs",
                    provider, url, exc, attempt + 1, retries, delay,
                )
                time.sleep(delay)
                continue
            logger.error(
                "[%s] connection error on POST %s persisted after %d retries (%s)",
                provider, url, retries, exc,
            )
            raise

        if is_transient_status(response.status_code) and attempt < retries:
            if is_hard_quota_response(response.status_code, response.text):
                # Daily/hourly allocation spent — retrying until the quota
                # window resets would just stall the caller.  Fail fast so the
                # caller can degrade gracefully instead.
                logger.error(
                    "[%s] HTTP %s reports a spent quota window on POST %s — "
                    "not retrying (backoff cannot reset a daily allocation)",
                    provider, response.status_code, url,
                )
                return response
            delay = base * (2 ** attempt)
            logger.warning(
                "[%s] transient HTTP %s on POST %s — retry %d/%d in %.1fs",
                provider, response.status_code, url, attempt + 1, retries, delay,
            )
            last_response = response
            time.sleep(delay)
            continue

        # 200, a permanent error, or transient-with-no-budget-left: hand back.
        return response

    # Only reachable if every attempt was transient and the budget ran out.
    return last_response  # type: ignore[return-value]
