-- Migration: 002_memory_store
-- Phase 11 — Memory store: structured case records + similarity retrieval.
-- Run against your Supabase project via the SQL editor (same as 001).

-- =============================================================================
-- 1. New enum
-- =============================================================================

CREATE TYPE memory_record_type AS ENUM ('case', 'correction');

-- =============================================================================
-- 2. memory_records table
--
-- Each CLOSED case writes one structured record (design.md "Memory records"):
--   evidence_gathered  — the 4 skill results (log correlation, OTX, deviation)
--   attack_technique   — mapped ATT&CK ID
--   verdict            — cross-checked FP/TP with confidence
--   reasoning          — plain-language explanation
--   response_taken     — action + outcome (JSON audit record)
--   mode               — agentic or approval
--   analyst_correction — what changed and why, if overridden (Phase 13)
--   record_type        — 'case' or 'correction'; corrections are retrieved
--                        with higher priority/weight for similar alerts
--
-- Denormalized retrieval keys (iocs, source_ip, asset_tags) are extracted
-- from the alert payload at write time for similarity matching.
-- =============================================================================

CREATE TABLE memory_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_type         memory_record_type NOT NULL DEFAULT 'case',
    alert_id            UUID REFERENCES alerts (id) ON DELETE CASCADE,
    case_id             UUID REFERENCES cases (id) ON DELETE SET NULL,
    source_alert_id     TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence_gathered   JSONB NOT NULL DEFAULT '{}',
    attack_technique    TEXT,
    verdict             verdict NOT NULL,
    confidence          FLOAT NOT NULL,
    reasoning           TEXT,
    response_taken      JSONB,
    mode                case_mode NOT NULL,
    analyst_correction  TEXT,
    -- Denormalized retrieval keys
    iocs                JSONB NOT NULL DEFAULT '[]',
    source_ip           TEXT,
    asset_tags          JSONB NOT NULL DEFAULT '[]'
);

COMMENT ON TABLE memory_records IS 'Structured investigation records for the agents'' memory store — written on case close, retrieved before new investigations.';

-- =============================================================================
-- 3. Indexes — retrieval paths
-- =============================================================================

CREATE INDEX idx_memory_records_alert_type  ON memory_records (alert_type);
CREATE INDEX idx_memory_records_created_at  ON memory_records (created_at DESC);
CREATE INDEX idx_memory_records_record_type ON memory_records (record_type);
CREATE INDEX idx_memory_records_source_ip   ON memory_records (source_ip);
