"""Arranque: python -m uvicorn app.main:app --reload (desde backend/)."""

from __future__ import annotations

from functools import partial
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.controllers.simulation_controller import router
from app.controllers.transfer_controller import router as transfer_router
from app.controllers.ephemeris_controller import router as ephemeris_router
from app.models.domain import SCHEMA_VERSION
from app.services.mock_simulation import MOCK_WARNING, build_mock_components
from app.services.simulation_service import SimulationComponents, run_simulation

DEFAULT_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:3000", "http://127.0.0.1:3000",
]


def create_app(
    *,
    simulation_mode: str | None = None,
    components: SimulationComponents | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    mode = simulation_mode if simulation_mode is not None else os.getenv("ORBITAL_SIMULATION_MODE", "mock")
    if mode not in {"mock", "real"}:
        raise ValueError("ORBITAL_SIMULATION_MODE debe ser 'mock' o 'real'.")
    if components is None and mode == "mock":
        components = build_mock_components()
    if cors_origins is None:
        origins_env = os.getenv("ORBITAL_CORS_ORIGINS")
        cors_origins = (
            list(DEFAULT_ORIGINS) if origins_env is None
            else [origin.strip() for origin in origins_env.split(",") if origin.strip()]
        )

    app = FastAPI(
        title="ORBITAL 4B — Backend de Rafa",
        version="0.1.0",
        description=(
            f"Modo actual: {mode}. En modo mock se devuelven DATOS FICTICIOS para React. "
            "El motor orbital real se conectará mediante adaptadores."
        ),
    )
    app.state.simulation_mode = mode
    app.state.simulation_runner = partial(run_simulation, components=components)

    @app.middleware("http")
    async def identify_simulation_mode(request: Request, call_next):
        response = await call_next(request)
        effective_mode = "real" if request.url.path.rstrip("/") in {"/transfers", "/transfers/optimize", "/transfers/lunar-orbit-return"} or request.url.path.rstrip("/") == "/ephemeris/earth-moon" else mode
        response.headers["X-Simulation-Mode"] = effective_mode
        if effective_mode == "mock":
            response.headers["X-Simulation-Warning"] = MOCK_WARNING
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Simulation-Mode", "X-Simulation-Warning"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # No devolvemos input ni ctx: pueden contener NaN/Infinity o excepciones
        # que no son serializables. Un dato inválido siempre debe dar 422.
        errors = [
            {"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": {
            "code": "invalid_request",
            "message": "Revisa los datos de la petición.",
            "errors": errors,
        }})

    @app.get("/health", tags=["Estado"])
    def health() -> dict:
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "simulation_mode": mode,
            "simulation_ready": components is not None,
            "notice": (
                "DATOS FICTICIOS: sin gravedad, RK2 ni detección de colisiones."
                if mode == "mock" else
                "Motor real conectado." if components is not None else
                "Motor real pendiente de conexión."
            ),
        }

    app.include_router(router)
    app.include_router(transfer_router)
    app.include_router(ephemeris_router)
    return app


app = create_app()
