from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_database
from app.routers import audit, graph, provision, routes, sites, ws
from app.services.monitor import get_monitor


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    init_database(settings.sqlite_db_path)
    monitor = get_monitor(settings)
    await monitor.start()

    yield

    # Shutdown
    await monitor.stop()


app = FastAPI(
    title="SiteFlow Dashboard API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router)
app.include_router(graph.router)
app.include_router(audit.router)
app.include_router(provision.router)
app.include_router(routes.router)
app.include_router(ws.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}
