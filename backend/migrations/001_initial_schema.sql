-- Migration: 001_initial_schema
-- Autonomous SOC Analyst Framework — Supabase dashboard schema
-- Run against your Supabase project via the SQL editor or CLI.

-- =============================================================================
-- 1. Custom enum types
-- =============================================================================

CREATE TYPE alert_status AS ENUM ('pending', 'in_review', 'closed');

CREATE TYPE case_mode AS ENUM ('agentic', 'approval');

CREATE TYPE verdict AS ENUM ('false_positive', 'true_positive');

CREATE TYPE secondary_verdict AS ENUM ('false_positive', 'true_positive', 'agree', 'disagree');

CREATE TYPE impact_level AS ENUM ('standard', 'high_impact');

CREATE TYPE action_status AS ENUM ('none', 'executed', 'escalated', 'awaiting_approval');

CREATE TYPE analyst_decision AS ENUM ('approved', 'redirected', 'self_acted');

-- =============================================================================
-- 2. Tables
-- =============================================================================

-- -----------------------------------------------------------------------------
-- alerts: raw incoming alerts before any agent processing
-- -----------------------------------------------------------------------------
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_alert_id TEXT        NOT NULL,
    alert_type      TEXT        NOT NULL,
    raw_payload     JSONB       NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          alert_status NOT NULL DEFAULT 'pending'
);

COMMENT ON TABLE  alerts IS 'Raw incoming alerts from the GUIDE dataset replay or external feed.';
COMMENT ON COLUMN alerts.source_alert_id IS 'Original ID from GUIDE dataset or external feed.';

-- -----------------------------------------------------------------------------
-- cases: one investigation case per alert (primary + secondary agent run)
-- -----------------------------------------------------------------------------
CREATE TABLE cases (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id                UUID            NOT NULL REFERENCES alerts (id) ON DELETE CASCADE,
    mode                    case_mode       NOT NULL,
    primary_verdict         verdict         NOT NULL,
    primary_confidence      FLOAT           NOT NULL,
    secondary_verdict       secondary_verdict,
    attack_technique        TEXT,
    impact_level            impact_level    NOT NULL,
    action_taken            TEXT,
    action_status           action_status   NOT NULL DEFAULT 'none',
    closed_at               TIMESTAMPTZ,
    qoder_memory_record_id  TEXT
);

COMMENT ON TABLE cases IS 'Investigation case per alert — tracks both agents'' verdicts and the response action.';

-- -----------------------------------------------------------------------------
-- analyst_overrides: logged when a human analyst overrides the agent's suggestion
-- -----------------------------------------------------------------------------
CREATE TABLE analyst_overrides (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID            NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
    original_suggestion TEXT            NOT NULL,
    analyst_decision    analyst_decision NOT NULL,
    analyst_action      TEXT,
    analyst_reasoning   TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

COMMENT ON TABLE analyst_overrides IS 'Analyst approve/redirect/self-act decisions with stated reasoning.';

-- -----------------------------------------------------------------------------
-- firewall_flags: log-poisoning / sanitization flags raised before agent processing
-- -----------------------------------------------------------------------------
CREATE TABLE firewall_flags (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id    UUID        NOT NULL REFERENCES alerts (id) ON DELETE CASCADE,
    flag_reason TEXT        NOT NULL,
    raw_snippet TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE firewall_flags IS 'Flags raised by the log-sanitization firewall before alerts reach the agents.';

-- =============================================================================
-- 3. Indexes — commonly queried fields
-- =============================================================================

-- Alerts
CREATE INDEX idx_alerts_status      ON alerts (status);
CREATE INDEX idx_alerts_received_at ON alerts (received_at DESC);

-- Cases
CREATE INDEX idx_cases_alert_id   ON cases (alert_id);
CREATE INDEX idx_cases_mode       ON cases (mode);
CREATE INDEX idx_cases_closed_at  ON cases (closed_at DESC) WHERE closed_at IS NOT NULL;

-- Analyst overrides
CREATE INDEX idx_analyst_overrides_case_id    ON analyst_overrides (case_id);
CREATE INDEX idx_analyst_overrides_created_at ON analyst_overrides (created_at DESC);

-- Firewall flags
CREATE INDEX idx_firewall_flags_alert_id    ON firewall_flags (alert_id);
CREATE INDEX idx_firewall_flags_created_at  ON firewall_flags (created_at DESC);
