"""
APIBridge AI - Main FastAPI Application
Entry point for the backend server.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path

from .database.db import init_db
from .routes import apis, changes, adapters, proxy, tests_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle event handler: runs on server startup and shutdown.
    Ensures SQLite tables are initialized before handling requests.
    """
    print("[APIBridge AI] Initializing database tables...")
    init_db()
    print("[APIBridge AI] Database ready!")
    yield
    print("[APIBridge AI] Server shutting down.")


app = FastAPI(
    title="APIBridge AI Backend",
    description="Autonomous Breaking-Change Detection & Dynamic Adapter Proxy Generator",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS (Cross-Origin Resource Sharing) so React frontend can communicate seamlessly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routes
app.include_router(apis.router)
app.include_router(changes.router)
app.include_router(adapters.router)
app.include_router(proxy.router)
app.include_router(tests_runner.router)


# Frontend Dist Path
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@app.get("/")
def root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "project": "APIBridge AI",
        "description": "Autonomous Breaking-Change Detection & Dynamic Adapter Proxy Generator",
        "version": "1.0.0",
        "docs_url": "/docs",
        "health_check": "/health",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "APIBridge AI Core",
        "database": "SQLite (Connected)",
    }


# Mount Built React Frontend Static Assets if dist exists
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
