"""POST /simulations: validación HTTP y llamada al servicio de Rafa."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.schemas import SimulationRequest, SimulationResponse
from app.services.simulation_service import (
    InvalidSimulationInputError, SimulationLimitError, SimulationNotReadyError,
    SimulationRunner, UnknownScenarioError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulations", tags=["Simulación"])


def get_simulation_runner(request: Request) -> SimulationRunner:
    """Se puede reemplazar en las pruebas sin modificar el controlador."""
    return request.app.state.simulation_runner


def _error_example(code: str, message: str) -> dict:
    return {"application/json": {"example": {"detail": {"code": code, "message": message}}}}


@router.post(
    "",
    response_model=SimulationResponse,
    summary="Ejecutar una simulación (datos ficticios en modo mock)",
    description=(
        "El modo inicial es mock: la nave se mueve en línea recta, sin gravedad ni RK2. "
        "Lee X-Simulation-Mode y X-Simulation-Warning y muestra el aviso en React. "
        "El cuerpo mantiene el contrato SimulationResult. Límite: 10 000 pasos. "
        "collision y numerical_error son resultados de simulación con HTTP 200."
    ),
    responses={
        200: {"headers": {
            "X-Simulation-Mode": {"schema": {"type": "string", "enum": ["mock", "real"]}},
            "X-Simulation-Warning": {"schema": {"type": "string"}, "description": "Aviso de datos ficticios en modo mock."},
        }},
        404: {"description": "Escenario desconocido.", "content": _error_example("unknown_scenario", "Escenario desconocido.")},
        422: {"description": "Petición inválida, estado no representable o límite de pasos.", "content": _error_example("invalid_request", "Revisa los datos de la petición.")},
        503: {"description": "Motor real pendiente de conexión.", "content": _error_example("simulation_not_ready", "El motor real aún no está conectado.")},
        500: {"description": "Fallo interno o salida incompatible con el contrato.", "content": _error_example("simulation_failed", "No se pudo completar la ejecución.")},
    },
)
def simulate(
    payload: Annotated[SimulationRequest, Body(openapi_examples={
        "mock": {
            "summary": "Prueba ficticia para React",
            "value": {
                "scenario_id": "mock_earth_moon_v1",
                "initial_state": {"position_m": [2000000, 0, 0], "velocity_m_s": [0, 7500, 0]},
                "duration_s": 60, "step_s": 10,
            },
        },
    })],
    runner: Annotated[SimulationRunner, Depends(get_simulation_runner)],
) -> SimulationResponse:
    try:
        config = payload.to_domain()
        result = runner(config)
        return SimulationResponse.from_domain(result)
    except UnknownScenarioError as exc:
        raise HTTPException(404, detail={"code": "unknown_scenario", "message": str(exc)}) from exc
    except SimulationLimitError as exc:
        raise HTTPException(422, detail={"code": "simulation_limit_exceeded", "message": str(exc)}) from exc
    except InvalidSimulationInputError as exc:
        raise HTTPException(422, detail={"code": "invalid_initial_state", "message": str(exc)}) from exc
    except SimulationNotReadyError as exc:
        raise HTTPException(503, detail={"code": "simulation_not_ready", "message": str(exc)}) from exc
    except Exception as exc:
        logger.exception("Fallo de simulación o resultado incompatible con el contrato.")
        raise HTTPException(500, detail={
            "code": "simulation_failed", "message": "No se pudo completar la ejecución.",
        }) from exc
