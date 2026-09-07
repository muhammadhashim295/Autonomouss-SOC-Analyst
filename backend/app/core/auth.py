"""Authentication and Multi-Tenant IAM Scoping module.

Handles Supabase JWT validation, user profile resolution, tenant org_id
resolution, and creation of RLS-scoped Supabase client instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, Query, Request, status
from supabase import Client, ClientOptions, create_client

from app.core.config import settings
from app.db.supabase_client import get_supabase


@dataclass
class CurrentUser:
    """Authenticated user context with resolved tenant organization and IAM role."""

    id: str
    email: str
    role: str  # "client" or "admin"
    org_id: Optional[str]  # UUID, None for admin
    org_code: Optional[str]  # e.g., "UBL", "INDUS", "SMIU", None for admin
    org_name: Optional[str]  # Organization display name
    token: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_client(self) -> bool:
        return self.role == "client"


def get_scoped_supabase(user: CurrentUser) -> Client:
    """Return a Supabase client authenticated with the user's JWT Bearer token.

    PostgREST evaluates Row Level Security (RLS) directly in PostgreSQL based on
    this user token (auth.uid()).
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    if user and user.token:
        client.postgrest.auth(user.token)
    return client


def extract_token_from_request(
    authorization: Optional[str] = Header(None),
    token_param: Optional[str] = Query(None, alias="token"),
) -> Optional[str]:
    """Extract Bearer token from the Authorization header or ?token= query parameter."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if token_param:
        return token_param.strip()
    return None


async def get_current_user(
    token: Optional[str] = Depends(extract_token_from_request),
) -> CurrentUser:
    """FastAPI dependency to require and resolve an authenticated user and their tenant."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    supabase = get_supabase()

    try:
        user_response = supabase.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_obj = getattr(user_response, "user", None)
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found for the provided token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = getattr(user_obj, "id", None) or user_obj.get("id")
    email = getattr(user_obj, "email", "") or user_obj.get("email", "")

    # Look up profile from profiles table
    role = "client"
    org_id = None
    org_code = None
    org_name = None

    try:
        profile_res = (
            supabase.table("profiles")
            .select("*, organizations(id, name, code, sector)")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if profile_res.data:
            prof = profile_res.data[0]
            role = prof.get("role", "client")
            org_id = prof.get("org_id")
            org_info = prof.get("organizations")
            if org_info:
                org_code = org_info.get("code")
                org_name = org_info.get("name")
    except Exception:
        # Fallback to user_metadata if profiles query fails or during initial bootstrapping
        meta = getattr(user_obj, "user_metadata", {}) or {}
        role = meta.get("role", "client")
        org_code = meta.get("org_code")

    return CurrentUser(
        id=str(user_id),
        email=email,
        role=role,
        org_id=str(org_id) if org_id else None,
        org_code=org_code,
        org_name=org_name,
        token=token,
    )


async def get_optional_user(
    token: Optional[str] = Depends(extract_token_from_request),
) -> Optional[CurrentUser]:
    """FastAPI dependency for endpoints that optionally accept authentication."""
    if not token:
        return None
    try:
        return await get_current_user(token=token)
    except HTTPException:
        return None
