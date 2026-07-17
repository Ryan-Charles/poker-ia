from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import install_api, make_lifespan


def frontend_directory() -> Path:
    configured = os.environ.get("POKER_IA_FRONTEND_DIST")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app() -> FastAPI:
    application = FastAPI(
        title="Poker IA API",
        version=__version__,
        description=(
            "API locale d'entraînement avec jetons fictifs. Les conseils sont des estimations, "
            "jamais des certitudes sur les cartes inconnues."
        ),
        lifespan=make_lifespan(),
    )
    install_api(application)
    frontend = frontend_directory()
    if frontend.is_dir() and (frontend / "index.html").is_file():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    else:

        @application.get("/", include_in_schema=False)
        async def root() -> JSONResponse:
            return JSONResponse(
                {
                    "application": "Poker IA",
                    "api": "/docs",
                    "status": "backend prêt; frontend/dist absent",
                }
            )

    return application


app = create_app()
