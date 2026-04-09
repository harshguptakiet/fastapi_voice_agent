import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401
from app.core.config import APP_NAME, ENV
from app.core.validation import validate_configuration
from app.core.database import Base, engine
from app.routers.agent import router as agent_router
from app.routers.status import router as status_router
from app.routers.voice import router as voice_router
from app.routers.documents import router as documents_router
from app.routers.knowledge import router as knowledge_router
from app.services.runtime_clients import runtime_clients
from app.services.retrieval_cache_service import retrieval_cache_service

def create_app() -> FastAPI:
    validate_configuration()

    application = FastAPI(title=APP_NAME)

    base_dir = Path(__file__).resolve().parent
    static_dir = base_dir / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


    # Rate limiting middleware
    from app.core.rate_limit import SimpleRateLimiter
    application.add_middleware(SimpleRateLimiter)

    # CORS: wildcard + credentials=true is invalid per Fetch; use credentials only with explicit origins.
    _cors = (os.getenv("CORS_ALLOW_ORIGINS") or "*").strip()
    if _cors == "*":
        _allow_origins = ["*"]
        _allow_credentials = False
    else:
        _allow_origins = [o.strip() for o in _cors.split(",") if o.strip()]
        _allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").strip().lower() in {
            "1",
            "true",
            "yes",
        }
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_allow_origins,
        allow_credentials=_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers

    from app.routers.health import router as health_router
    application.include_router(agent_router)
    application.include_router(voice_router)
    application.include_router(status_router)
    application.include_router(documents_router)
    application.include_router(knowledge_router)
    application.include_router(health_router)

    @application.get("/")
    def ui_home():
        return RedirectResponse(url="/static/index.html")

    return application


app = create_app()


@app.on_event("startup")
async def on_startup():
    # In production, run migrations instead.
    if ENV.lower() == "dev":
        Base.metadata.create_all(bind=engine)
    await runtime_clients.startup()
    await retrieval_cache_service.startup()


@app.on_event("shutdown")
async def on_shutdown():
    await runtime_clients.shutdown()
    await retrieval_cache_service.shutdown()
