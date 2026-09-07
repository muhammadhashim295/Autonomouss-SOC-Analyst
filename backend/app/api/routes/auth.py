"""Authentication and Organization management endpoints."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.auth import CurrentUser, get_current_user
from app.db.supabase_client import get_supabase

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]
    profile: dict[str, Any]
    organization: Optional[dict[str, Any]] = None


@router.post("/auth/login", response_model=LoginResponse)
@router.post("/auth/login/", response_model=LoginResponse, include_in_schema=False)
async def login(req: LoginRequest) -> LoginResponse:
    """Authenticate user with Supabase Auth, returning access token, profile and tenant org."""
    supabase = get_supabase()

    try:
        auth_res = supabase.auth.sign_in_with_password(
            {
                "email": req.email.strip(),
                "password": req.password,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        ) from exc

    session = getattr(auth_res, "session", None)
    user = getattr(auth_res, "user", None)

    if not session or not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or inactive session.",
        )

    user_id = str(user.id)
    email = str(user.email)

    # Fetch profile and organization
    role = "client"
    org_id = None
    org_data = None

    try:
        prof_res = (
            supabase.table("profiles")
            .select("*, organizations(*)")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if prof_res.data:
            prof = prof_res.data[0]
            role = prof.get("role", "client")
            org_id = prof.get("org_id")
            org_data = prof.get("organizations")
    except Exception:
        meta = getattr(user, "user_metadata", {}) or {}
        role = meta.get("role", "client")
        org_code = meta.get("org_code")
        if org_code:
            try:
                org_res = supabase.table("organizations").select("*").eq("code", org_code).limit(1).execute()
                if org_res.data:
                    org_data = org_res.data[0]
                    org_id = org_data["id"]
            except Exception:
                pass

    return LoginResponse(
        access_token=session.access_token,
        token_type="bearer",
        user={
            "id": user_id,
            "email": email,
            "user_metadata": getattr(user, "user_metadata", {}),
        },
        profile={
            "id": user_id,
            "role": role,
            "org_id": org_id,
        },
        organization=org_data,
    )


@router.get("/auth/me")
async def get_me(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    """Return the current authenticated user session and tenant organization details."""
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_admin": user.is_admin,
        "is_client": user.is_client,
        "org_id": user.org_id,
        "org_code": user.org_code,
        "org_name": user.org_name,
    }


@router.get("/organizations")
async def list_organizations() -> list[dict[str, Any]]:
    """List all available organizations (UBL Digital Bank, Indus Health, SMIU)."""
    supabase = get_supabase()
    try:
        res = supabase.table("organizations").select("*").order("name").execute()
        return res.data or []
    except Exception as exc:
        # Fallback to predefined seed list if table not created yet
        return [
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
