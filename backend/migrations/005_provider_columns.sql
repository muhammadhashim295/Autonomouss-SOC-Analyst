-- Autonomous SOC Analyst Framework — migration 005
-- Final three-provider architecture: record which provider ran each agent.
-- Run against your Supabase project via the SQL editor (same as 001-004).

-- =============================================================================
-- primary_provider / secondary_provider on cases
--
-- The system now runs on three independent free-tier providers, one per role:
--   Primary Alert Triage Agent    -> Groq            (primary_provider   = 'groq')
--   Secondary Deep Investigation  -> Cerebras        (secondary_provider = 'cerebras')
--   Live alert generator          -> Cloudflare Workers AI
--
-- These columns make it unambiguous which provider actually ran a given
-- investigation.  Both are nullable so existing rows — and primary-only
-- /triage runs where the secondary never executed — remain valid.
--
-- Provider provenance is ALSO written into cases.investigation_snapshot
-- (JSONB, migration 004) by the action pipeline, so it is recorded even
-- before this migration is applied.  The backend inserts cases defensively:
-- if these columns are absent it retries without them and logs a warning.
-- =============================================================================

ALTER TABLE cases ADD COLUMN IF NOT EXISTS primary_provider   TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS secondary_provider TEXT;

COMMENT ON COLUMN cases.primary_provider   IS 'Provider that ran the Primary Alert Triage Agent (groq).';
COMMENT ON COLUMN cases.secondary_provider IS 'Provider that ran the Secondary Deep Investigation Agent (cerebras); NULL until the secondary runs.';
