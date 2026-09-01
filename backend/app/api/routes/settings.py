"""Phase 12 — Settings API: global mode toggle endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.settings_store import get_mode, set_mode

router = APIRouter(prefix="/settings", tags=["settings"])


class ModeResponse(BaseModel):
    mode: Literal["agentic", "approval"]


class ModeUpdateRequest(BaseModel):
    mode: Literal["agentic", "approval"]


@router.get("/mode", response_model=ModeResponse)
async def read_mode() -> ModeResponse:
    """Return the current global mode (agentic or approval)."""
    return ModeResponse(mode=get_mode())


@router.put("/mode", response_model=ModeResponse)
async def update_mode(request: ModeUpdateRequest) -> ModeResponse:
    """Set the global mode.

    - ``agentic``: standard actions execute autonomously when the
      cross-checked verdict is confident (high-impact still always
      requires approval)
    - ``approval``: ALL action decisions (standard included) pause for
      analyst review
    """
    try:
        mode = set_mode(request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface storage errors
        raise HTTPException(status_code=502, detail=f"Mode update failed: {exc}") from exc
    return ModeResponse(mode=mode)
