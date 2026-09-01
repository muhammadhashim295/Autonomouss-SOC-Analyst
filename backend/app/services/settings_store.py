"""Phase 12 — Global mode toggle (agentic / approval) persistence.

Storage: the ``system_settings`` Supabase table (migration 003), key
``mode``.  The global value is what NEW cases inherit (snapshotted onto
``cases.mode`` at persist time by :func:`persist_case`).

Fail-safe: any storage error returns the built-in default
(``"agentic"`` — matches behavior through Phase 11) rather than failing
an investigation.  ``set_mode`` raises so the API can surface toggle
errors to the caller explicitly.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

Mode = Literal["agentic", "approval"]

_MODE_KEY = "mode"
_DEFAULT_MODE: Mode = "agentic"
_VALID_MODES = {"agentic", "approval"}


def get_mode() -> Mode:
    """Return the current global mode ('agentic' or 'approval').

    Falls back to 'agentic' if the setting is missing or the store is
    unreachable — investigations must never block on the toggle.
    """
    try:
        supabase = get_supabase()
        result = (
            supabase.table("system_settings")
            .select("value")
            .eq("key", _MODE_KEY)
            .limit(1)
            .execute()
        )
        if result.data:
            value = result.data[0].get("value")
            if value in _VALID_MODES:
                return value  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001 — toggle must never block flow
        logger.warning("Mode lookup failed, defaulting to %s: %s", _DEFAULT_MODE, exc)
    return _DEFAULT_MODE


def set_mode(mode: str) -> Mode:
    """Set the global mode.  Raises ValueError on an invalid mode."""
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}' — must be 'agentic' or 'approval'"
        )

    supabase = get_supabase()
    # Upsert: insert the key if absent, update if present
    result = (
        supabase.table("system_settings")
        .upsert({"key": _MODE_KEY, "value": mode}, on_conflict="key")
        .execute()
    )
    if not result.data:
        raise RuntimeError("Mode upsert returned no rows")

    logger.info("Global mode set to %s", mode)
    return mode  # type: ignore[return-value]
