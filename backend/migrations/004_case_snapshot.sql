-- Migration: 004_case_snapshot
-- Phase 13 — Persist the full investigation snapshot on the case row.
-- Run against your Supabase project via the SQL editor (same as 001-003).

-- =============================================================================
-- investigation_snapshot: both agents' parsed output + the 4-skill
-- enrichment, persisted when the action pipeline runs.  Used by:
--   - Phase 13 analyst decisions (deferred memory write at decision time
--     needs the investigation data for the correction record)
--   - Phase 15 frontend case-detail screen (both agents' reasoning chains)
-- =============================================================================

ALTER TABLE cases ADD COLUMN investigation_snapshot JSONB;

COMMENT ON COLUMN cases.investigation_snapshot IS 'Full investigation snapshot (primary/secondary parsed output + skill enrichment) persisted at action-pipeline time — source for deferred memory writes and the frontend case detail view.';
