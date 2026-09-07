"""Provision client organizations, admin & client accounts, and user profiles.

Run this script once after executing `migrations/006_multitenancy_rls.sql`
in the Supabase SQL Editor.
"""

from __future__ import annotations

import sys
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.db.supabase_client import get_supabase


ACCOUNTS_CONFIG = [
    {
        "email": "ubl-analyst@ubl.com.pk",
        "password": "UBL@Analyst2026!",
        "role": "client",
        "org_code": "UBL",
        "name": "UBL Lead SecOps Analyst",
    },
    {
        "email": "ubl@soc.local",
        "password": "UBL_soc_secure_2026!",
        "role": "client",
        "org_code": "UBL",
        "name": "UBL SecOps Analyst",
    },
    {
        "email": "indus-analyst@indus.health",
        "password": "Indus@Analyst2026!",
        "role": "client",
        "org_code": "INDUS",
        "name": "Indus Hospital SecOps Analyst",
    },
    {
        "email": "indus@soc.local",
        "password": "Indus_soc_secure_2026!",
        "role": "client",
        "org_code": "INDUS",
        "name": "Indus Health SecOps Analyst",
    },
    {
        "email": "smiu-analyst@smiu.edu.pk",
        "password": "SMIU@Analyst2026!",
        "role": "client",
        "org_code": "SMIU",
        "name": "SMIU IT Security Analyst",
    },
    {
        "email": "smiu@soc.local",
        "password": "SMIU_soc_secure_2026!",
        "role": "client",
        "org_code": "SMIU",
        "name": "SMIU IT Security Analyst",
    },
    {
        "email": "client@soc.local",
        "password": "Client@SOC2026!",
        "role": "client",
        "org_code": "UBL",
        "name": "Default Test Client Analyst",
    },
    {
        "email": "admin@soc.local",
        "password": "Admin@SOC2026!",
        "role": "admin",
        "org_code": None,
        "name": "Central SOC Super Admin",
    },
]

ORGANIZATIONS_CONFIG = [
    {
        "name": "UBL Digital Bank",
        "sector": "FINANCIAL SECTOR",
        "code": "UBL",
    },
    {
        "name": "Indus Health Network",
        "sector": "HEALTHCARE SECTOR",
        "code": "INDUS",
    },
    {
        "name": "Sindh Madressatul Islam University",
        "sector": "EDUCATION SECTOR",
        "code": "SMIU",
    },
]


def setup():
    supabase = get_supabase()
    print("Connecting to Supabase at:", settings.supabase_url)

    # 1. Verify organizations table exists
    try:
        orgs_res = supabase.table("organizations").select("*").execute()
    except Exception as exc:
        print("\n[ERROR] Table 'organizations' not found.")
        print("Please run backend/migrations/006_multitenancy_rls.sql in your Supabase SQL Editor first!")
        print(f"Details: {exc}")
        sys.exit(1)

    # Seed organizations if empty or missing
    existing_orgs = {org["code"]: org for org in orgs_res.data or []}
    for org_data in ORGANIZATIONS_CONFIG:
        code = org_data["code"]
        if code not in existing_orgs:
            ins = supabase.table("organizations").insert(org_data).execute()
            print(f"Created organization: {org_data['name']} ({code})")
            existing_orgs[code] = ins.data[0]
        else:
            print(f"Organization already exists: {org_data['name']} ({code}) -> {existing_orgs[code]['id']}")

    # 2. Provision Accounts in Supabase Auth
    print("\n--- Provisioning Accounts via Supabase Auth Admin ---")
    auth_users = supabase.auth.admin.list_users()
    existing_users = {u.email.lower(): u for u in auth_users if getattr(u, "email", None)}

    for acc in ACCOUNTS_CONFIG:
        email = acc["email"].lower()
        org_code = acc["org_code"]
        org_id = existing_orgs[org_code]["id"] if org_code else None
        role = acc["role"]
        user_id = None

        if email in existing_users:
            user = existing_users[email]
            user_id = user.id
            print(f"Auth user already exists: {email} (id: {user_id})")
        else:
            # Create user with confirmed email
            new_user_res = supabase.auth.admin.create_user(
                {
                    "email": email,
                    "password": acc["password"],
                    "email_confirm": True,
                    "user_metadata": {
                        "name": acc["name"],
                        "role": role,
                        "org_code": org_code,
                    },
                }
            )
            # The returned UserResponse has user property
            user_obj = getattr(new_user_res, "user", new_user_res)
            user_id = user_obj.id if hasattr(user_obj, "id") else user_obj["id"]
            print(f"Created auth user: {email} (id: {user_id})")

        # 3. Upsert profile in profiles table
        profile_row = {
            "id": user_id,
            "org_id": org_id,
            "role": role,
        }
        try:
            supabase.table("profiles").upsert(profile_row).execute()
            print(f"  -> Profile synced for {email} (role: {role}, org_id: {org_id})")
        except Exception as exc:
            print(f"  -> [WARNING] Failed to sync profile for {email}: {exc}")

    # 4. Backfill any unassigned alerts, cases, flags, memory records
    ubl_org = existing_orgs.get("UBL")
    if ubl_org:
        ubl_id = ubl_org["id"]
        print(f"\n--- Ensuring legacy demo records are assigned to UBL ({ubl_id}) ---")
        for tbl in ["alerts", "cases", "analyst_overrides", "firewall_flags", "memory_records"]:
            try:
                # Update records where org_id is null
                res = supabase.table(tbl).update({"org_id": ubl_id}).is_("org_id", "null").execute()
                count = len(res.data) if res.data else 0
                print(f"  -> Table '{tbl}': backfilled {count} legacy records to UBL.")
            except Exception as exc:
                print(f"  -> [NOTE] Table '{tbl}' backfill check: {exc}")

    print("\n[SUCCESS] Multi-tenancy accounts and profiles setup complete!")


if __name__ == "__main__":
    setup()
