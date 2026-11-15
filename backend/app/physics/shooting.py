"""Corrección tridimensional de una velocidad inicial mediante shooting."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from app.models.domain import Vec3, validate_positive, validate_vec3

ArrivalResidual = Callable[[Vec3], Vec3]


@dataclass(frozen=True)
class ShootingResult:
    initial_velocity_m_s: Vec3
    arrival_residual_m: Vec3
    residual_norm_m: float
    converged: bool
    evaluations: int
    message: str


def solve_shooting(
    initial_velocity_guess_m_s: Vec3,
    arrival_residual: ArrivalResidual,
    *,
    velocity_scale_m_s: float = 1_000.0,
    residual_scale_m: float = 1_000.0,
    arrival_tolerance_m: float = 1_000.0,
    max_evaluations: int = 100,
    planar: bool = False,
) -> ShootingResult:
    """Ajusta la velocidad para anular el error de posición final.

    ``arrival_residual(v)`` debe propagar la nave con la velocidad ``v`` y
    devolver ``posición_nave_final - posición_objetivo_final`` en metros. El
    callback permite reutilizar RK2 ahora y cambiar de integrador más adelante.
    Con planar=True ajusta únicamente vx y vy mediante Levenberg–Marquardt,
    fija vz=0 y resuelve el residuo XY, como en el documento de referencia.
    """

    validate_vec3(initial_velocity_guess_m_s, "initial_velocity_guess_m_s")
    validate_positive(velocity_scale_m_s, "velocity_scale_m_s")
    validate_positive(residual_scale_m, "residual_scale_m")
    validate_positive(arrival_tolerance_m, "arrival_tolerance_m")
    if isinstance(max_evaluations, bool) or not isinstance(max_evaluations, int) or max_evaluations <= 0:
        raise ValueError("max_evaluations debe ser un entero positivo.")
    if not callable(arrival_residual):
        raise TypeError("arrival_residual debe ser invocable.")

    initial = np.asarray(initial_velocity_guess_m_s, dtype=float) / velocity_scale_m_s
    if planar:
        initial = initial[:2]

    def normalized_residual(normalized_velocity: np.ndarray) -> np.ndarray:
        velocity = tuple(float(value * velocity_scale_m_s) for value in normalized_velocity)
        if planar:
            velocity = (*velocity, 0.0)
        residual = arrival_residual(velocity)  # type: ignore[arg-type]
        validate_vec3(residual, "arrival_residual")
        return np.asarray(residual[:2] if planar else residual, dtype=float) / residual_scale_m

    solver_tolerance = max(1e-14, min(1e-7, arrival_tolerance_m / residual_scale_m * 0.01))
    optimization = least_squares(
        normalized_residual,
        initial,
        method="lm" if planar else "trf",
        max_nfev=max_evaluations,
        xtol=solver_tolerance,
        ftol=solver_tolerance,
        gtol=solver_tolerance,
    )

    velocity = tuple(float(value * velocity_scale_m_s) for value in optimization.x)
    if planar:
        velocity = (*velocity, 0.0)
    residual = tuple(float(value) for value in arrival_residual(velocity))  # type: ignore[arg-type]
    validate_vec3(residual, "arrival_residual")
    residual_norm = float(np.linalg.norm(residual))
    return ShootingResult(
        initial_velocity_m_s=velocity,  # type: ignore[arg-type]
        arrival_residual_m=residual,  # type: ignore[arg-type]
        residual_norm_m=residual_norm,
        converged=bool(optimization.success and residual_norm <= arrival_tolerance_m),
        evaluations=int(optimization.nfev),
        message=str(optimization.message),
    )
