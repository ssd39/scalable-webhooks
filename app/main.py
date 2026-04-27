import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.routes import webhook as webhook_router
from app.api.routes import jobs as jobs_router
from app.api.routes import shipments as shipments_router
from app.api.routes import invoices as invoices_router
from app.api.routes import unclassified as unclassified_router
from app.db.database import dispose_engine
from app.services.redis_client import ping_redis

logging.basicConfig(
    level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.APP_DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting up %s v%s …", settings.APP_NAME, settings.APP_VERSION)
    # DB migrations are handled by Alembic (run before server starts)
    if ping_redis():
        logger.info("Redis connection OK – %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)
    else:
        logger.warning("Redis is NOT reachable – tasks will fail to enqueue!")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down – releasing resources …")
    await dispose_engine()


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(webhook_router.router)
app.include_router(jobs_router.router)
app.include_router(shipments_router.router)
app.include_router(invoices_router.router)
app.include_router(unclassified_router.router)

# ---------------------------------------------------------------------------
# Health / root endpoints
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    return JSONResponse({"name": settings.APP_NAME, "version": settings.APP_VERSION, "status": "ok"})


@app.get("/health", tags=["Health"])
async def health() -> JSONResponse:
    redis_ok = ping_redis()
    return JSONResponse(
        {
            "status": "ok" if redis_ok else "degraded",
            "redis": "ok" if redis_ok else "unreachable",
        }
    )
