"""API del cálculo de transferencias reales; el objeto C(t) vive en servicio."""
from typing import Literal

from fastapi import APIRouter, HTTPException
import numpy as np
from pydantic import BaseModel, Field, AwareDatetime

from app.data.ephemeris import EphemerisError
from app.services.transfer_service import TransferNotFoundError, design_transfer, optimize_transfer, TransferResult

router = APIRouter(prefix="/transfers", tags=["Transferencias"])


class TransferRequest(BaseModel):
    date: AwareDatetime
    duration_s: float = Field(default=864000, gt=0, le=30 * 86400, allow_inf_nan=False)
    launch_angle_deg: float = Field(default=90, allow_inf_nan=False)
    arrival_angle_deg: float = Field(default=0, allow_inf_nan=False)
    objective: Literal["energia", "distancia"] = "energia"
    mass_kg: float = Field(default=1, gt=0, allow_inf_nan=False)
    samples: int = Field(default=200, ge=2, le=4000)


@router.post("")
def transfer(request: TransferRequest):
    """Calcula F con Horizons (también si /simulations está en modo mock)."""
    try:
        result = design_transfer(
            request.date, request.duration_s,
            launch_angle_deg=request.launch_angle_deg,
            arrival_angle_deg=request.arrival_angle_deg,
            objective=request.objective, mass_kg=request.mass_kg,
        )
    except EphemerisError as error:
        raise HTTPException(502, str(error)) from error
    except (TransferNotFoundError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return serialize_transfer(result, request, arrival_angle_deg=request.arrival_angle_deg)


def _serialize_samples(result: TransferResult, duration_s: float, count: int) -> list[dict]:
    times = np.linspace(0.0, duration_s, count)
    solution = getattr(result, "_solution", None)
    sol_fn = getattr(solution, "sol", None)
    bodies = result.scenario.bodies

    if callable(sol_fn):
        states = sol_fn(times)
        xs, ys, vxs, vys = (
            states[0].tolist(),
            states[1].tolist(),
            states[2].tolist(),
            states[3].tolist(),
        )
        body_tracks: dict[str, list[list[float]]] = {}
        for key, body in bodies.items():
            pos_array = getattr(body, "pos_array", None)
            if callable(pos_array):
                body_tracks[key] = pos_array(times).tolist()
            else:
                body_tracks[key] = [list(body.pos(float(t))) for t in times]

        times_list = times.tolist()
        return [
            {
                "t_s": times_list[i],
                "position_m": [xs[i], ys[i], 0.0],
                "velocity_m_s": [vxs[i], vys[i], 0.0],
                "body_positions_m": {key: track[i] for key, track in body_tracks.items()},
            }
            for i in range(count)
        ]

    # Fallback para objetos simulados en pruebas unitarias sin _solution densa.
    return [
        {
            "t_s": float(t),
            "position_m": result.pos(float(t)),
            "velocity_m_s": result.speed(float(t)),
            "body_positions_m": {key: body.pos(float(t)) for key, body in bodies.items()},
        }
        for t in times
    ]


def serialize_transfer(
    result: TransferResult, request: TransferRequest, *, arrival_angle_deg: float,
) -> dict:
    """Contrato compartido entre la ruta clásica y la búsqueda angular."""
    return {
        "source": "NASA/JPL Horizons", "date": request.date,
        "frame": "earth_moon_barycentric_initial_orbital_plane",
        "basis_icrf": result.scenario.basis_icrf.tolist(),
        "objective": result.objective, "mass_kg": result.mass_kg,
        "arrival_angle_deg": arrival_angle_deg,
        "initial_velocity_m_s": result.initial_velocity_m_s,
        "launch_speed_m_s": result.launch_speed_m_s,
        "launch_energy_j": result.launch_energy_j,
        "path_length_m": result.path_length_m,
        "arrival_error_m": result.arrival_error_m,
        "duration_s": request.duration_s,
        "bodies": {key: {"name": body.name, "radius_m": body.radius_m}
                   for key, body in result.scenario.bodies.items()},
        "samples": _serialize_samples(result, request.duration_s, request.samples),
    }


class OptimizeTransferRequest(BaseModel):
    date: AwareDatetime
    duration_s: float = Field(default=864000, gt=0, le=30 * 86400, allow_inf_nan=False)
    launch_angle_deg: float = Field(default=90, allow_inf_nan=False)
    objective: Literal["energia", "distancia"] = "energia"
    mass_kg: float = Field(default=1, gt=0, allow_inf_nan=False)
    samples: int = Field(default=200, ge=2, le=4000)


@router.post("/optimize")
def optimize(request: OptimizeTransferRequest):
    """Busca el mejor sobrevuelo terminal evaluado con una duración fija."""
    try:
        optimized = optimize_transfer(
            request.date, request.duration_s,
            launch_angle_deg=request.launch_angle_deg,
            objective=request.objective, mass_kg=request.mass_kg,
        )
    except EphemerisError as error:
        raise HTTPException(502, str(error)) from error
    except TransferNotFoundError as error:
        raise HTTPException(status_code=422, detail={
            "code": "no_valid_transfer",
            "message": str(error),
            "suggestion": "Prueba otra fecha o duración. Una búsqueda acotada sin resultados no demuestra que la trayectoria sea imposible.",
        }) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_transfer_parameters", "message": str(error),
        }) from error
    payload = serialize_transfer(optimized.transfer, request, arrival_angle_deg=optimized.arrival_angle_deg)
    payload["optimization"] = {
        "method": "bounded_angle_search",
        "attempted_angles_deg": optimized.attempted_angles_deg,
        "valid_candidates": optimized.valid_candidates,
        "search_complete": optimized.search_complete,
        "timed_out_angles_deg": optimized.timed_out_angles_deg,
        "global_optimum_guaranteed": False,
    }
    return payload