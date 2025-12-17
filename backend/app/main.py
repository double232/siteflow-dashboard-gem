from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import init_database
from app.routers import audit, backups, deploy, graph, health, provision, routes, sites, ws
from app.services.monitor import get_monitor


settings = get_settings()
STATIC_DIR = Path(__file__).parent.parent / "static"


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

# Parse CORS origins from settings
# Default restricts to localhost dev servers; in production set CORS_ALLOWED_ORIGINS env var
cors_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

app.include_router(sites.router)
app.include_router(graph.router)
app.include_router(audit.router)
app.include_router(provision.router)
app.include_router(routes.router)
app.include_router(deploy.router)
app.include_router(ws.router)
app.include_router(health.router)
app.include_router(backups.router)


@app.get("/api/ping")
async def ping():
    """Simple health check for load balancers."""
    return {"status": "ok", "version": "0.2.0"}


# Custom 404 handler - serve SPA for non-API routes
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    """Serve SPA for non-API 404s, return JSON for API 404s."""
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/ws"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    # Serve SPA for all other 404s
    if STATIC_DIR.exists():
        return FileResponse(STATIC_DIR / "index.html")
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# Serve static files (frontend)
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(STATIC_DIR / "index.html")

    # Serve other static files (vite.svg, etc)
    @app.get("/{filename}")
    async def serve_static_file(filename: str):
        file_path = STATIC_DIR / filename
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
