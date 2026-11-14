"""API del cálculo de transferencias reales; el objeto C(t) vive en servicio."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, AwareDatetime

from app.data.ephemeris import EphemerisError
from app.services.transfer_service import TransferNotFoundError, design_transfer

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
    except TransferNotFoundError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "source": "NASA/JPL Horizons", "date": request.date,
        "frame": "earth_moon_barycentric_initial_orbital_plane",
        "basis_icrf": result.scenario.basis_icrf.tolist(),
        "objective": result.objective, "mass_kg": result.mass_kg,
        "initial_velocity_m_s": result.initial_velocity_m_s,
        "launch_speed_m_s": result.launch_speed_m_s,
        "launch_energy_j": result.launch_energy_j,
        "path_length_m": result.path_length_m,
        "arrival_error_m": result.arrival_error_m,
        "samples": [
            {"t_s": t, "position_m": result.pos(t), "velocity_m_s": result.speed(t),
             "body_positions_m": {key: body.pos(t) for key, body in result.scenario.bodies.items()}}
            for t in (request.duration_s * i / (request.samples - 1) for i in range(request.samples))
        ],
    }
