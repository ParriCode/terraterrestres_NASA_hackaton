"""API del cálculo de transferencias reales (ida y retorno Tierra–Luna–Tierra)."""

from fastapi import APIRouter, HTTPException
import numpy as np
from pydantic import BaseModel, Field, AwareDatetime

from app.data.ephemeris import EphemerisError
from app.services.transfer_service import TransferNotFoundError, design_transfer, optimize_transfer, TransferResult
from app.services.lunar_mission_service import design_lunar_orbit_return

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
        "source": "NASA/JPL Horizons",
        "date": request.date,
        "frame": frame,
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

class LunarOrbitReturnRequest(BaseModel):
    """Inserción en órbita lunar, revoluciones configurables y regreso terrestre."""
    date: AwareDatetime
    duration_s: float = Field(default=10 * 86400, ge=4 * 86400, le=30 * 86400, allow_inf_nan=False)
    objective: Literal["energia", "distancia"] = "energia"
    mass_kg: float = Field(default=1000, gt=0, allow_inf_nan=False)
    launch_angle_deg: float = Field(default=90, allow_inf_nan=False)
    orbit_altitude_km: float = Field(default=100, ge=50, le=500, allow_inf_nan=False)
    lunar_revolutions: int = Field(default=1, ge=1, le=100, strict=True)
    samples: int = Field(default=450, ge=100, le=4000)


@router.post("/lunar-orbit-return")
def lunar_orbit_return(request: LunarOrbitReturnRequest):
    """Propaga ida, inserción orbital, órbita y retorno propulsado.

    Si no se valida un candidato dentro del presupuesto, responde 422.
    Nunca devuelve una ruta de retorno visual inventada.
    """
    try:
        return design_lunar_orbit_return(
            request.date, request.duration_s, objective=request.objective,
            mass_kg=request.mass_kg, samples=request.samples,
            orbit_altitude_km=request.orbit_altitude_km,
            lunar_revolutions=request.lunar_revolutions,
            launch_angle_deg=request.launch_angle_deg,
        )
    except EphemerisError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except TransferNotFoundError as error:
        raise HTTPException(status_code=422, detail={
            "code": "no_valid_lunar_orbit_return", "message": str(error),
            "suggestion": "Prueba otra fecha, duración o altitud lunar. La búsqueda acotada no prueba imposibilidad física.",
        }) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_lunar_mission", "message": str(error),
        }) from error
