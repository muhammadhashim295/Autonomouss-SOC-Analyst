"""Python enums mirroring the Postgres custom types defined in 001_initial_schema.sql."""

from enum import Enum


class AlertStatus(str, Enum):
    pending = "pending"
    in_review = "in_review"
    closed = "closed"


class CaseMode(str, Enum):
    agentic = "agentic"
    approval = "approval"


class Verdict(str, Enum):
    false_positive = "false_positive"
    true_positive = "true_positive"


class SecondaryVerdict(str, Enum):
    false_positive = "false_positive"
    true_positive = "true_positive"
    agree = "agree"
    disagree = "disagree"


class ImpactLevel(str, Enum):
    standard = "standard"
    high_impact = "high_impact"


class ActionStatus(str, Enum):
    none = "none"
    executed = "executed"
    escalated = "escalated"
    awaiting_approval = "awaiting_approval"


class AnalystDecision(str, Enum):
    approved = "approved"
    redirected = "redirected"
    self_acted = "self_acted"
