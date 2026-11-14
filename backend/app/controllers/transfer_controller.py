"""API del cálculo de transferencias reales; el objeto C(t) vive en servicio."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.data.ephemeris import EphemerisError
from app.services.mission_optimizer import (
    DEFAULT_PARKING_ALT_M,
    NoFeasibleTransfer,
    optimize_transfer,
)
from app.services.propulsion import estimate_propellant
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


class OptimizeTransferRequest(BaseModel):
    date: AwareDatetime
    max_duration_s: float = Field(default=10 * 86400, gt=0, le=30 * 86400, allow_inf_nan=False)
    parking_alt_m: float = Field(default=DEFAULT_PARKING_ALT_M, ge=0, le=50_000_000, allow_inf_nan=False)
    samples: int = Field(default=200, ge=2, le=4000)
    initial_mass_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    isp_s: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_propulsion_pair(self):
        if (self.initial_mass_kg is None) != (self.isp_s is None):
            raise ValueError("initial_mass_kg e isp_s deben proporcionarse juntos.")
        return self


def _sample_times(duration_s: float, count: int):
    for i in range(count):
        if i == 0:
            yield 0.0
        elif i == count - 1:
            yield float(duration_s)
        else:
            yield float(duration_s * i / (count - 1))


def _serialize_tradeoff(tradeoff):
    return [
        {
            "duration_s": point.duration_s,
            "estimated_launch_delta_v_m_s": point.estimated_launch_delta_v_m_s,
            "estimated_arrival_delta_v_m_s": point.estimated_arrival_delta_v_m_s,
            "estimated_total_delta_v_m_s": point.estimated_total_delta_v_m_s,
        }
        for point in tradeoff
    ]


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
        "duration_s": request.duration_s,
        "bodies": {key: {"name": body.name, "radius_m": body.radius_m}
                   for key, body in result.scenario.bodies.items()},
        "samples": [
            {"t_s": t, "position_m": result.pos(t), "velocity_m_s": result.speed(t),
             "body_positions_m": {key: body.pos(t) for key, body in result.scenario.bodies.items()}}
            for t in _sample_times(request.duration_s, request.samples)
        ],
    }


@router.post("/optimize")
def optimize(request: OptimizeTransferRequest):
    """Optimiza Δv total Tierra→Luna sujeto a tiempo máximo de vuelo."""
    mass_kg = request.initial_mass_kg if request.initial_mass_kg is not None else 1.0
    try:
        opt = optimize_transfer(
            request.date,
            request.max_duration_s,
            parking_alt_m=request.parking_alt_m,
            mass_kg=mass_kg,
        )
    except EphemerisError as error:
        raise HTTPException(502, str(error)) from error
    except NoFeasibleTransfer as error:
        return {
            "status": "no_feasible_solution",
            "source": "NASA/JPL Horizons",
            "date": request.date,
            "max_duration_s": request.max_duration_s,
            "min_search_duration_s": error.min_duration_s,
            "parking_alt_m": request.parking_alt_m,
            "reasons": error.reasons,
            "tradeoff": _serialize_tradeoff(error.tradeoff),
        }
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    result = opt.transfer
    propellant_payload = None
    if request.initial_mass_kg is not None and request.isp_s is not None:
        prop = estimate_propellant(
            request.initial_mass_kg, result.total_delta_v_m_s, request.isp_s
        )
        propellant_payload = {
            "initial_mass_kg": prop.initial_mass_kg,
            "isp_s": prop.isp_s,
            "propellant_mass_kg": prop.propellant_mass_kg,
            "final_mass_kg": prop.final_mass_kg,
            "mass_fraction": prop.mass_fraction,
            "idealized": True,
        }

    return {
        "status": "ok",
        "source": "NASA/JPL Horizons",
        "date": request.date,
        "frame": "earth_moon_barycentric_initial_orbital_plane",
        "basis_icrf": result.scenario.basis_icrf.tolist(),
        "objective": "delta_v",
        "mass_kg": result.mass_kg,
        "duration_s": result.t1_s,
        "max_duration_s": request.max_duration_s,
        "min_search_duration_s": opt.min_duration_s,
        "parking_alt_m": request.parking_alt_m,
        "launch_angle_deg": opt.best_candidate.launch_angle_deg,
        "arrival_angle_deg": opt.best_candidate.arrival_angle_deg,
        "initial_velocity_m_s": result.initial_velocity_m_s,
        "launch_speed_m_s": result.launch_speed_m_s,
        "launch_delta_v_m_s": result.launch_delta_v_m_s,
        "arrival_v_infinity_m_s": result.arrival_v_infinity_m_s,
        "arrival_delta_v_m_s": result.arrival_delta_v_m_s,
        "total_delta_v_m_s": result.total_delta_v_m_s,
        "launch_energy_j": result.launch_energy_j,
        "path_length_m": result.path_length_m,
        "arrival_error_m": result.arrival_error_m,
        "propellant": propellant_payload,
        "tradeoff": _serialize_tradeoff(opt.tradeoff),
        "bodies": {
            key: {"name": body.name, "radius_m": body.radius_m}
            for key, body in result.scenario.bodies.items()
        },
        "samples": [
            {
                "t_s": t,
                "position_m": result.pos(t),
                "velocity_m_s": result.speed(t),
                "body_positions_m": {
                    key: body.pos(t) for key, body in result.scenario.bodies.items()
                },
            }
            for t in _sample_times(result.t1_s, request.samples)
        ],
    }