"""MSDS Lab web entry point.

Build the frontend first: npm --prefix web ci && npm --prefix web run build
Run: uvicorn app.main:app --reload
Register model API routes before the static mount when serving is implemented.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="MSDS Lab", version="0.1.0")

# Serve the compiled frontend only; JSX source and training data stay outside.
web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if not (web_dist / "index.html").is_file():
    raise RuntimeError(
        "Frontend build missing. Run npm --prefix web ci, "
        "then npm --prefix web run build before starting FastAPI."
    )
app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
