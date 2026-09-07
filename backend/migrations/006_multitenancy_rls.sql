-- Autonomous SOC Analyst Framework — migration 006
-- Multi-tenancy: 3 client organizations (UBL, INDUS, SMIU) + 1 admin account
-- Row Level Security (RLS) data isolation + profile linking.

-- =============================================================================
-- 1. Organizations table
-- =============================================================================

CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    sector      TEXT NOT NULL,
    code        TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE organizations IS 'Client organizations monitored by the Autonomous SOC Analyst Framework.';

-- Seed the 3 client organizations if not already present
INSERT INTO organizations (name, sector, code)
VALUES
    ('UBL Digital Bank', 'FINANCIAL SECTOR', 'UBL'),
    ('Indus Health Network', 'HEALTHCARE SECTOR', 'INDUS'),
    ('Sindh Madressatul Islam University', 'EDUCATION SECTOR', 'SMIU')
ON CONFLICT (code) DO NOTHING;

-- =============================================================================
-- 2. Profiles table (linked to auth.users)
-- =============================================================================

CREATE TABLE IF NOT EXISTS profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    org_id      UUID REFERENCES organizations (id) ON DELETE SET NULL,
    role        TEXT NOT NULL CHECK (role IN ('client', 'admin')) DEFAULT 'client',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE profiles IS 'User profile linking Supabase auth.users to their client organization and role.';

-- =============================================================================
-- 3. Add org_id to core tables & backfill pre-existing demo records
-- =============================================================================

-- 3.1 Alerts
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_org_id ON alerts (org_id);

-- 3.2 Cases
ALTER TABLE cases ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_cases_org_id ON cases (org_id);

-- 3.3 Analyst Overrides
ALTER TABLE analyst_overrides ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_analyst_overrides_org_id ON analyst_overrides (org_id);

-- 3.4 Firewall Flags
ALTER TABLE firewall_flags ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_firewall_flags_org_id ON firewall_flags (org_id);

-- 3.5 Memory Records
ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_memory_records_org_id ON memory_records (org_id);

-- Backfill pre-existing data with UBL Digital Bank's org_id
DO $$
DECLARE
    ubl_id UUID;
BEGIN
    SELECT id INTO ubl_id FROM organizations WHERE code = 'UBL' LIMIT 1;
    IF ubl_id IS NOT NULL THEN
        UPDATE alerts SET org_id = ubl_id WHERE org_id IS NULL;
        UPDATE cases SET org_id = ubl_id WHERE org_id IS NULL;
        UPDATE analyst_overrides SET org_id = ubl_id WHERE org_id IS NULL;
        UPDATE firewall_flags SET org_id = ubl_id WHERE org_id IS NULL;
        UPDATE memory_records SET org_id = ubl_id WHERE org_id IS NULL;
    END IF;
END $$;

-- =============================================================================
-- 4. Helper Functions for Row Level Security
-- =============================================================================

CREATE OR REPLACE FUNCTION get_auth_user_role()
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

CREATE OR REPLACE FUNCTION get_auth_user_org_id()
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT org_id FROM public.profiles WHERE id = auth.uid();
$$;

-- =============================================================================
-- 5. Enable Row Level Security (RLS) & Policies
-- =============================================================================

-- Organizations: all authenticated users can view organizations
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "organizations_select_policy" ON organizations;
CREATE POLICY "organizations_select_policy" ON organizations
    FOR SELECT TO authenticated
    USING (true);

-- Profiles: users can read their own profile, admin can read all
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "profiles_select_policy" ON profiles;
CREATE POLICY "profiles_select_policy" ON profiles
    FOR SELECT TO authenticated
    USING (
        id = auth.uid()
        OR get_auth_user_role() = 'admin'
    );

DROP POLICY IF EXISTS "profiles_insert_update_policy" ON profiles;
CREATE POLICY "profiles_insert_update_policy" ON profiles
    FOR ALL TO authenticated
    USING (get_auth_user_role() = 'admin')
    WITH CHECK (get_auth_user_role() = 'admin');

-- Alerts: client can only access own org; admin accesses all
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "alerts_select_policy" ON alerts;
CREATE POLICY "alerts_select_policy" ON alerts
    FOR SELECT TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

DROP POLICY IF EXISTS "alerts_insert_policy" ON alerts;
CREATE POLICY "alerts_insert_policy" ON alerts
    FOR INSERT TO authenticated
    WITH CHECK (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

DROP POLICY IF EXISTS "alerts_update_policy" ON alerts;
CREATE POLICY "alerts_update_policy" ON alerts
    FOR UPDATE TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

-- Cases: client can only access own org; admin accesses all
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cases_select_policy" ON cases;
CREATE POLICY "cases_select_policy" ON cases
    FOR SELECT TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

DROP POLICY IF EXISTS "cases_insert_policy" ON cases;
CREATE POLICY "cases_insert_policy" ON cases
    FOR INSERT TO authenticated
    WITH CHECK (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

DROP POLICY IF EXISTS "cases_update_policy" ON cases;
CREATE POLICY "cases_update_policy" ON cases
    FOR UPDATE TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

-- Analyst Overrides: scoped by org_id (or joined through cases)
ALTER TABLE analyst_overrides ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "analyst_overrides_policy" ON analyst_overrides;
CREATE POLICY "analyst_overrides_policy" ON analyst_overrides
    FOR ALL TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
        OR EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = analyst_overrides.case_id
            AND (cases.org_id = get_auth_user_org_id() OR get_auth_user_role() = 'admin')
        )
    );

-- Firewall Flags: scoped by org_id (or joined through alerts)
ALTER TABLE firewall_flags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "firewall_flags_policy" ON firewall_flags;
CREATE POLICY "firewall_flags_policy" ON firewall_flags
    FOR ALL TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
        OR EXISTS (
            SELECT 1 FROM alerts
            WHERE alerts.id = firewall_flags.alert_id
            AND (alerts.org_id = get_auth_user_org_id() OR get_auth_user_role() = 'admin')
        )
    );

-- Memory Records: scoped by org_id
ALTER TABLE memory_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "memory_records_select_policy" ON memory_records;
CREATE POLICY "memory_records_select_policy" ON memory_records
    FOR SELECT TO authenticated
    USING (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

DROP POLICY IF EXISTS "memory_records_insert_policy" ON memory_records;
CREATE POLICY "memory_records_insert_policy" ON memory_records
    FOR INSERT TO authenticated
    WITH CHECK (
        get_auth_user_role() = 'admin'
        OR org_id = get_auth_user_org_id()
    );

-- =============================================================================
-- 6. Permissions Grant
-- =============================================================================

GRANT USAGE ON SCHEMA public TO authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated, service_role;
