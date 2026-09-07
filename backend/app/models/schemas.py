"""Pydantic models matching the four Supabase tables (design.md schema).

These are used for request/response validation in later phases.  Field names
and types mirror the SQL migration exactly.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ActionStatus,
    AlertStatus,
    AnalystDecision,
    CaseMode,
    ImpactLevel,
    SecondaryVerdict,
    Verdict,
)


# ── organizations ────────────────────────────────────────────────────────────


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    sector: str
    code: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── alerts ────────────────────────────────────────────────────────────────────


class AlertBase(BaseModel):
    source_alert_id: str
    alert_type: str
    raw_payload: dict[str, Any]
    status: AlertStatus = AlertStatus.pending
    org_id: Optional[UUID] = None


class AlertCreate(AlertBase):
    """Payload for inserting a new alert."""


class AlertResponse(AlertBase):
    id: UUID
    received_at: datetime

    model_config = {"from_attributes": True}


# ── cases ─────────────────────────────────────────────────────────────────────


class CaseBase(BaseModel):
    alert_id: UUID
    mode: CaseMode
    primary_verdict: Verdict
    primary_confidence: float = Field(ge=0.0, le=1.0)
    secondary_verdict: Optional[SecondaryVerdict] = None
    attack_technique: Optional[str] = None
    impact_level: ImpactLevel
    action_taken: Optional[str] = None
    action_status: ActionStatus = ActionStatus.none
    qoder_memory_record_id: Optional[str] = None
    # Provider provenance (migration 005): which provider ran each agent.
    # Primary is always Groq; Secondary is always Cerebras in the final
    # three-provider architecture.  Optional so rows written before the
    # migration (or before the secondary ran) still validate.
    primary_provider: Optional[str] = None
    secondary_provider: Optional[str] = None
    org_id: Optional[UUID] = None


class CaseCreate(CaseBase):
    """Payload for inserting a new case."""


class CaseResponse(CaseBase):
    id: UUID
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── analyst_overrides ─────────────────────────────────────────────────────────


class AnalystOverrideBase(BaseModel):
    case_id: UUID
    original_suggestion: str
    analyst_decision: AnalystDecision
    analyst_action: Optional[str] = None
    analyst_reasoning: Optional[str] = None
    org_id: Optional[UUID] = None


class AnalystOverrideCreate(AnalystOverrideBase):
    """Payload for logging an analyst override."""


class AnalystOverrideResponse(AnalystOverrideBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── firewall_flags ────────────────────────────────────────────────────────────


class FirewallFlagBase(BaseModel):
    alert_id: UUID
    flag_reason: str
    raw_snippet: Optional[str] = None
    org_id: Optional[UUID] = None


class FirewallFlagCreate(FirewallFlagBase):
    """Payload for recording a firewall flag."""


class FirewallFlagResponse(FirewallFlagBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── health check ──────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    supabase_url: str
    alerts_count: Optional[int] = None
    error: Optional[str] = None


# ── secondary re-investigation (Phase 8) ──────────────────────────────────────


class ReinvestigateRequest(BaseModel):
    """Optional body for POST /alerts/{id}/reinvestigate.

    If ``primary_report`` is omitted, the endpoint runs the Primary Agent
    first, then feeds its output to the Secondary Agent.
    """

    primary_report: Optional[str] = None
    primary_verdict: Optional[str] = None
    primary_confidence: Optional[float] = None
