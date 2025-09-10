from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from timz_app.api.v1.router import api_router

app = FastAPI(title="Timz API", version="0.1.0")

# CORS (dev only – on resserrera en prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Debug helpers (utile en dev; commente-les si tu veux)
from fastapi.routing import APIRoute


@app.get("/__where")
async def where():
    import pathlib
    import sys

    return {
        "file": str(pathlib.Path(__file__).resolve()),
        "cwd": str(pathlib.Path().resolve()),
        "sys_path_head": sys.path[:5],
    }


@app.get("/__routes")
async def routes():
    return [{"path": r.path} for r in app.router.routes if isinstance(r, APIRoute)]


# API v1
app.include_router(api_router, prefix="/api/v1")
