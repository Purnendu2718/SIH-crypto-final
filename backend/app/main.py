"""CryptoTrace Sentinel — Main FastAPI Application Entry Point.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import (
    auth,
    cases,
    analysis,
    evidence,
    correlator,
    watchlist,
    vasp_admin,
    intel,
    arjuna,
    websocket_trace,
    search,
    tagpack_admin,
    legal,
    intake,
)




@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-initialize database tables for pure-local / offline execution
    init_db()
    try:
        from app.fixtures.seed_fixtures import seed_vasp_directory
        seed_vasp_directory()
    except Exception as e:
        print(f"VASP auto-seed note: {e}")
    try:
        from app.database import SessionLocal
        from app.models import Profile, EntityLabel
        from app.services.tagpack_ingest import ingest_from_seed_file
        db = SessionLocal()
        if db.query(Profile).count() == 0:
            from app.routers.cases import seed_demo_cases
            seed_demo_cases(db)
        if db.query(EntityLabel).count() == 0:
            ingest_from_seed_file(db)
        db.close()
    except Exception as e:
        print(f"Startup auto-seed note: {e}")
    yield


app = FastAPI(
    title="CryptoTrace Sentinel API",
    description="Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges (SIH26183)",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach Rate Limiting Middleware (protects auth & public endpoints)
from app.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Configure CORS for local and staging frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(cases.router_v1)
app.include_router(analysis.router)
app.include_router(evidence.router)
app.include_router(evidence.audit_router)
app.include_router(correlator.router)
app.include_router(watchlist.router)
app.include_router(vasp_admin.router)
app.include_router(intel.router)
app.include_router(arjuna.router)
app.include_router(websocket_trace.router)
app.include_router(websocket_trace.sse_router)
app.include_router(search.router)
app.include_router(tagpack_admin.router)
app.include_router(legal.router)
app.include_router(legal.router_v1)
app.include_router(intake.router)
app.include_router(intake.router_v1)





@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler returning structured JSON with HTTP 500."""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal Server Error",
            "detail": str(exc),
        },
    )


@app.get("/api/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """Health check endpoint for container orchestrators and load balancers."""
    return {
        "status": "ok",
        "app": "CryptoTrace Sentinel",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
    }

