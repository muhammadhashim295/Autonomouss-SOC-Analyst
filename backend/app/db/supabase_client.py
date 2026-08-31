"""Supabase client singleton — initialised once at import time."""

from supabase import Client, create_client

from app.core.config import settings

_client: Client | None = None

try:
    _client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
except Exception as exc:  # noqa: BLE001
    print(f"[supabase_client] Failed to initialise: {exc}")


def get_supabase() -> Client:
    """Return the shared Supabase client, raising if it was never created."""
    if _client is None:
        raise RuntimeError(
            "Supabase client is not initialised. "
            "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in your .env file."
        )
    return _client
