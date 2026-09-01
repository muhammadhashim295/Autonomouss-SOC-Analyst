-- Migration: 003_system_settings
-- Phase 12 — Global mode toggle (agentic / approval).
-- Run against your Supabase project via the SQL editor (same as 001/002).

-- =============================================================================
-- system_settings: simple key/value store for global framework settings.
-- The 'mode' key holds the global agentic/approval toggle.  Cases snapshot
-- the mode at investigation time (cases.mode); this table holds the
-- CURRENT global value that new cases inherit.
-- =============================================================================

CREATE TABLE system_settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE system_settings IS 'Global framework settings (key/value). Currently used for the agentic/approval mode toggle.';

-- Default: agentic mode (matches behavior through Phase 11)
INSERT INTO system_settings (key, value) VALUES ('mode', '"agentic"'::jsonb);
