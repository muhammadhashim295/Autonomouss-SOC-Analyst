"""Application configuration — loads environment variables via pydantic-settings."""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the backend/ root, not the working directory.
# config.py lives in backend/app/core/, so go up three levels.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"

load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Supabase (required) ───────────────────────────────────────────
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str

    # ── AlienVault OTX (required for IOC enrichment, Phase 6+) ────────
    otx_api_key: str = ""

    # ── Gemini (required for live feed generation, Phase 3b) ──────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── Qoder Cloud Agents ────────────────────────────────────────────
    qoder_pat: Optional[str] = None
    qoder_primary_agent_id: Optional[str] = None
    qoder_primary_env_id: Optional[str] = None
    qoder_api_base: str = "https://api.qoder.com/api/v1/cloud"

    # ── CORS ──────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
