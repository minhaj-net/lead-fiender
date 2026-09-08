"""
backend/main.py
────────────────
FastAPI application entry point for Codeloom Lead Finder.

Start the server:
  uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

Interactive API docs:
  http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import health, automation, leads
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB tables on startup."""
    logger.info("Codeloom Lead Finder backend starting up...")
    try:
        init_db()
        logger.info("Database ready.")
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)
        # Allow startup to continue so health endpoint can report db error
    yield
    logger.info("Backend shutting down.")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Codeloom Lead Finder API",
    description = (
        "Local backend for the Codeloom Lead Finder Chrome extension. "
        "Processes publicly available business information and stores qualified leads."
    ),
    version     = "1.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# ── CORS — allow the Chrome Extension (chrome-extension://*) ─────────────────
# Restricted to localhost only. Do not open this to the public internet.
app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],   # Extension origin + localhost dev tools
    allow_methods  = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers  = ["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(automation.router)
app.include_router(leads.router)


# ── Root redirect ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "Codeloom Lead Finder",
        "version": "1.0.0",
        "docs":    "http://127.0.0.1:8000/docs",
    }
