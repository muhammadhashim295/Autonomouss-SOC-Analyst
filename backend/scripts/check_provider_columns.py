"""Non-destructive check: are migration 005's provider columns present on `cases`?

Selects the two new columns with limit 1.  If PostgREST reports the column does
not exist, migration 005 has not been applied in the Supabase SQL editor yet.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase

try:
    s = get_supabase()
    r = s.table("cases").select("id,primary_provider,secondary_provider").limit(1).execute()
    print("COLUMNS OK -> migration 005 applied. sample row:", r.data)
except Exception as exc:  # noqa: BLE001
    print("MISSING/ERROR -> migration 005 likely NOT applied:", str(exc)[:240])
