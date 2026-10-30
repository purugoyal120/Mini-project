"""
APIBridge AI - Quick Server Launcher
Run this script to start the FastAPI server with hot-reload enabled.

Command:
    python run_backend.py
or
    .\\venv\\Scripts\\python.exe run_backend.py
"""

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  Starting APIBridge AI Backend on http://127.0.0.1:8000")
    print("  Swagger Interactive Docs: http://127.0.0.1:8000/docs")
    print("=" * 60)
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
