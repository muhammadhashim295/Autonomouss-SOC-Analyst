"""Autonomous SOC Analyst Framework — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.alerts import router as alerts_router
from app.api.routes.cases import router as cases_router
from app.api.routes.generate import router as generate_router
from app.api.routes.memory import router as memory_router
from app.api.routes.settings import router as settings_router
from app.api.routes.stream import router as stream_router
from app.core.config import settings
from app.db.supabase_client import get_supabase
from app.models.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks (reserved for later phases)."""
    yield


app = FastAPI(
    title="Autonomous SOC Analyst Framework",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Generate router must come before alerts router to avoid path-prefix conflicts
app.include_router(generate_router)
app.include_router(alerts_router)
app.include_router(settings_router)
app.include_router(cases_router)
app.include_router(memory_router)
app.include_router(stream_router)


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Verify the app is running **and** the Supabase connection is live.

    Performs a real ``SELECT count(*)`` against the ``alerts`` table so a
    successful response guarantees the DB round-trip works, not just that
    credentials are present.
    """
    try:
        client = get_supabase()
        response = client.table("alerts").select("*", count="exact").execute()
        alerts_count = response.count if response.count is not None else 0
        return HealthResponse(
            status="healthy",
            supabase_url=settings.supabase_url,
            alerts_count=alerts_count,
        )
    except RuntimeError as exc:
        # Supabase client was never initialised (bad / missing credentials)
        return HealthResponse(
            status="degraded",
            supabase_url=settings.supabase_url,
            error=f"Supabase client not initialised: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        # Client exists but the query failed (network, wrong URL, auth, etc.)
        return HealthResponse(
            status="unhealthy",
            supabase_url=settings.supabase_url,
            error=str(exc),
        )
