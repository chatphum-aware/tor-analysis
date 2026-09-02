from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.export import router as export_router
from app.api.extract import router as extract_router
from app.config import load_config

app = FastAPI(title="TOR Analyzer API")

config = load_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(extract_router)
app.include_router(export_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
