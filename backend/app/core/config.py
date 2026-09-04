"""Application configuration — loads environment variables via pydantic-settings."""

from pathlib import Path

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

    # ── Provider 1: Groq — Primary Alert Triage Agent ─────────────────
    # OpenAI-compatible Chat Completions API with SSE streaming.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # ── Provider 2: Cerebras — Secondary Deep Investigation Agent ─────
    # OpenAI-compatible Chat Completions API with SSE streaming.
    cerebras_api_key: str = ""
    cerebras_model: str = "gpt-oss-120b"

    # ── Provider 3: Cloudflare Workers AI — live alert generator ──────
    # REST: /client/v4/accounts/{account_id}/ai/run/{model}
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_model: str = "@cf/meta/llama-3.1-8b-instruct"
    # Output-token cap per generation.  Latency scales with this: ~8s at 1024
    # vs ~3-4s at 512 on the free tier.  512 keeps alert JSON complete while
    # staying fast enough for the concurrent pool to sustain the feed cadence.
    cloudflare_max_tokens: int = 512

    # ── Live feed cadence ──────────────────────────────────────────────
    # One new alert every N seconds (2-3s window; 3s is the stable default).
    live_feed_interval_seconds: int = 3
    # Fraction of generated alerts carrying a log-poisoning payload.
    live_feed_poison_ratio: float = 0.15
    # Number of concurrent Cloudflare generator workers.  A single call takes
    # ~3-8s, so one worker cannot sustain a 3s cadence on its own; a small pool
    # fills a queue that the inserter drains once per interval.
    live_feed_concurrency: int = 3

    # ── Provider retry policy (all three providers) ────────────────────
    # Exponential backoff on rate-limit / transient errors: 1s, 2s, 4s.
    provider_max_retries: int = 3
    provider_backoff_base_seconds: float = 1.0

    # ── Action execution (Phase 10) ────────────────────────────────────
    # Minimum cross-checked confidence before the secondary agent may
    # execute a standard action autonomously in agentic mode.
    action_confidence_threshold: float = 0.7

    # ── CORS ──────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
