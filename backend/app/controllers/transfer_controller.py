"""API del cálculo de transferencias reales (ida y retorno Tierra–Luna–Tierra)."""

from typing import Iterator, Literal
from threading import BoundedSemaphore
import os

import numpy as np

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.data.ephemeris import EphemerisError
from app.models.domain import REFERENCE_FRAME
from app.services.mission_optimizer import (
    DEFAULT_PARKING_ALT_M,
    NoFeasibleTransfer,
    optimize_transfer,
    optimize_round_trip_transfer,
)
from app.services.propulsion import estimate_propellant
from app.services.transfer_service import TransferNotFoundError, design_transfer
from app.transfer_schemas import OptimizedResponse, RoundTripResponse, TransferResponse

router = APIRouter(prefix="/transfers", tags=["Transferencias"])

# Un request CPU-intensivo ya se ejecuta en un worker por ser endpoint `def`.
# Este semáforo evita lanzar demasiados solvers simultáneos en un proceso.
_SOLVER_SLOTS = BoundedSemaphore(max(1, int(os.getenv("ORBITAL_MAX_CONCURRENT_SOLVERS", "2"))))


def _solver_slot() -> Iterator[None]:
    if not _SOLVER_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail={"code": "solver_busy", "message": "El optimizador está ocupado. Inténtalo de nuevo."},
            headers={"Retry-After": "5"},
        )
    try:
        yield
    finally:
        _SOLVER_SLOTS.release()



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


class RoundTripTransferRequest(BaseModel):
    """Petición para trayectoria completa Tierra → Luna → Tierra."""

    date: AwareDatetime
    mode: Literal["free_return", "lunar_orbit"] = "free_return"
    max_total_duration_s: float = Field(
        default=14 * 86400, gt=0, le=35 * 86400, allow_inf_nan=False
    )
    parking_alt_m: float = Field(
        default=DEFAULT_PARKING_ALT_M, ge=100_000, le=50_000_000, allow_inf_nan=False
    )
    lunar_periapsis_alt_m: float = Field(
        default=150_000.0, ge=20_000, le=10_000_000, allow_inf_nan=False
    )
    lunar_stay_s: float = Field(
        default=0.0, ge=0.0, le=14 * 86400, allow_inf_nan=False
    )
    reentry_alt_m: float = Field(
        default=120_000.0, ge=50_000, le=1_000_000, allow_inf_nan=False
    )
    samples: int = Field(default=300, ge=2, le=4000)
    initial_mass_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    isp_s: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_round_trip(self):
        if (self.initial_mass_kg is None) != (self.isp_s is None):
            raise ValueError("initial_mass_kg e isp_s deben proporcionarse juntos.")
        if self.mode == "free_return" and self.lunar_stay_s > 0:
            raise ValueError("El modo free_return no admite estancia orbital (lunar_stay_s > 0).")
        return self


def _time_grid(trajectory, duration_s: float, count: int) -> np.ndarray:
    """Mallas con nodos de maniobra sin cambiar el número de muestras solicitado."""
    segments = getattr(trajectory, "_segments", ())
    boundaries = sorted({float(start) for start, _, _ in segments[1:]
                         if 0 < start < duration_s})
    if not boundaries or count < 2 * len(boundaries) + 4:
        return np.linspace(0.0, duration_s, count, dtype=np.float64)
    # Dos nodos contiguos por impulso: permite mostrar velocidades pre/post
    # LOI/TEI sin que Hermite interpole el salto durante miles de segundos.
    marks = [0.0, duration_s]
    for t in boundaries:
        marks.extend((max(0.0, t - 0.05), t))
    mandatory = np.unique(np.asarray(marks, dtype=np.float64))
    inner = np.linspace(0.0, duration_s, count - len(mandatory) + 2)[1:-1]
    ts = np.unique(np.concatenate((mandatory, inner)))
    while len(ts) < count:
        gaps = np.diff(ts)
        i = int(np.argmax(gaps))
        ts = np.insert(ts, i + 1, (ts[i] + ts[i + 1]) / 2)
    return ts


def _serialize_samples(trajectory, duration_s: float, count: int) -> list[dict]:
    """Muestreo vectorizado de las soluciones densas y de splines de Horizons."""
    ts = _time_grid(trajectory, duration_s, count)
    if hasattr(trajectory, "_segments"):
        # Los cambios de velocidad en LOI/TEI son impulsos: el lado derecho
        # del salto prevalece en el instante de la maniobra.
        states = np.empty((count, 6), dtype=np.float64)
        for start, end, solution in trajectory._segments:
            mask = (ts >= start) & (ts <= end)
            if np.any(mask):
                states[mask] = solution.sol(ts[mask]).T
    else:
        planar = np.asarray(trajectory._solution.sol(ts), dtype=np.float64).T
        states = np.zeros((count, 6), dtype=np.float64)
        states[:, :2] = planar[:, :2]
        states[:, 3:5] = planar[:, 2:4]

    body_pos = {}
    for key, body in trajectory.scenario.bodies.items():
        motion = getattr(body, "_motion", None)
        if callable(motion):
            values = np.asarray(motion(ts), dtype=np.float64)
            if values.shape[1] == 2:
                values = np.column_stack((values, np.zeros(count)))
        else:
            values = np.asarray([body.pos(float(t)) for t in ts], dtype=np.float64)
        body_pos[key] = values
    return [
        {
            "t_s": float(t),
            "position_m": states[i, :3].tolist(),
            "velocity_m_s": states[i, 3:].tolist(),
            "body_positions_m": {key: arr[i].tolist() for key, arr in body_pos.items()},
        }
        for i, t in enumerate(ts)
    ]


def _domain_exception(status: int, code: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": str(exc)})


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


def _propellant_dict(initial_mass_kg: float | None, isp_s: float | None, total_dv: float):
    if initial_mass_kg is None or isp_s is None:
        return None
    prop = estimate_propellant(initial_mass_kg, total_dv, isp_s)
    return {
        "initial_mass_kg": prop.initial_mass_kg,
        "isp_s": prop.isp_s,
        "propellant_mass_kg": prop.propellant_mass_kg,
        "final_mass_kg": prop.final_mass_kg,
        "mass_fraction": prop.mass_fraction,
        "idealized": True,
    }


@router.post("", response_model=TransferResponse, dependencies=[Depends(_solver_slot)])
def transfer(request: TransferRequest):
    """Calcula transferencia Tierra → Luna con Horizons."""
    try:
        result = design_transfer(
            request.date,
            request.duration_s,
            launch_angle_deg=request.launch_angle_deg,
            arrival_angle_deg=request.arrival_angle_deg,
            objective=request.objective,
            mass_kg=request.mass_kg,
        )
    except EphemerisError as error:
        raise _domain_exception(502, "ephemeris_unavailable", error) from error
    except TransferNotFoundError as error:
        raise _domain_exception(422, "transfer_not_found", error) from error
    except ValueError as error:
        raise _domain_exception(422, "invalid_transfer", error) from error
    except (RuntimeError, ArithmeticError) as error:
        raise _domain_exception(503, "solver_failed", error) from error

    frame = getattr(result.scenario, "frame", REFERENCE_FRAME)
    return {
        "source": "NASA/JPL Horizons",
        "date": request.date,
        "frame": frame,
        "basis_icrf": result.scenario.basis_icrf.tolist(),
        "objective": result.objective,
        "mass_kg": result.mass_kg,
        "initial_velocity_m_s": result.initial_velocity_m_s,
        "launch_speed_m_s": result.launch_speed_m_s,
        "launch_energy_j": result.launch_energy_j,
        "path_length_m": result.path_length_m,
        "arrival_error_m": result.arrival_error_m,
        "duration_s": request.duration_s,
        "bodies": {
            key: {"name": body.name, "radius_m": body.radius_m}
            for key, body in result.scenario.bodies.items()
        },
        "samples": _serialize_samples(result, request.duration_s, request.samples),
    }


@router.post("/optimize", response_model=OptimizedResponse, dependencies=[Depends(_solver_slot)])
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
        raise _domain_exception(502, "ephemeris_unavailable", error) from error
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
        raise _domain_exception(422, "invalid_transfer", error) from error
    except (RuntimeError, ArithmeticError) as error:
        raise _domain_exception(503, "solver_failed", error) from error

    result = opt.transfer
    frame = getattr(result.scenario, "frame", REFERENCE_FRAME)
    return {
        "status": "ok",
        "source": "NASA/JPL Horizons",
        "date": request.date,
        "frame": frame,
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
        "propellant": _propellant_dict(
            request.initial_mass_kg, request.isp_s, result.total_delta_v_m_s
        ),
        "tradeoff": _serialize_tradeoff(opt.tradeoff),
        "bodies": {
            key: {"name": body.name, "radius_m": body.radius_m}
            for key, body in result.scenario.bodies.items()
        },
        "samples": _serialize_samples(result, result.t1_s, request.samples),
    }


@router.post("/round-trip", response_model=RoundTripResponse, dependencies=[Depends(_solver_slot)])
def round_trip(request: RoundTripTransferRequest):
    """Calcula trayectoria completa Tierra → Luna → Tierra (retorno libre u órbita lunar)."""
    mass_kg = request.initial_mass_kg if request.initial_mass_kg is not None else 1.0
    try:
        rt = optimize_round_trip_transfer(
            request.date,
            mode=request.mode,
            max_total_duration_s=request.max_total_duration_s,
            parking_alt_m=request.parking_alt_m,
            lunar_periapsis_alt_m=request.lunar_periapsis_alt_m,
            lunar_stay_s=request.lunar_stay_s,
            reentry_alt_m=request.reentry_alt_m,
            mass_kg=mass_kg,
        )
    except EphemerisError as error:
        raise _domain_exception(502, "ephemeris_unavailable", error) from error
    except NoFeasibleTransfer as error:
        return {
            "status": "no_feasible_solution",
            "source": "NASA/JPL Horizons",
            "mode": request.mode,
            "date": request.date,
            "max_total_duration_s": request.max_total_duration_s,
            "reasons": error.reasons,
        }
    except ValueError as error:
        raise _domain_exception(422, "invalid_transfer", error) from error
    except (RuntimeError, ArithmeticError) as error:
        raise _domain_exception(503, "solver_failed", error) from error

    frame = getattr(rt.scenario, "frame", REFERENCE_FRAME)
    return {
        "status": "ok",
        "source": "NASA/JPL Horizons",
        "mode": request.mode,
        "date": request.date,
        "frame": frame,
        "basis_icrf": rt.scenario.basis_icrf.tolist(),
        "outbound_duration_s": rt.outbound_duration_s,
        "lunar_stay_s": rt.lunar_stay_s,
        "inbound_duration_s": rt.inbound_duration_s,
        "total_duration_s": rt.total_duration_s,
        "tli_delta_v_m_s": rt.tli_delta_v_m_s,
        "loi_delta_v_m_s": rt.loi_delta_v_m_s,
        "tei_delta_v_m_s": rt.tei_delta_v_m_s,
        "total_delta_v_m_s": rt.total_delta_v_m_s,
        "min_lunar_altitude_m": rt.min_lunar_altitude_m,
        "earth_reentry_altitude_m": rt.earth_reentry_altitude_m,
        "propellant": _propellant_dict(
            request.initial_mass_kg, request.isp_s, rt.total_delta_v_m_s
        ),
        "bodies": {
            key: {"name": body.name, "radius_m": body.radius_m}
            for key, body in rt.scenario.bodies.items()
        },
        "samples": _serialize_samples(rt, rt.total_duration_s, request.samples),
    }