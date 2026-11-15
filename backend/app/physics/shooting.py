"""Corrección tridimensional de una velocidad inicial mediante shooting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

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
        velocity: Vec3 = (
            (float(normalized_velocity[0] * velocity_scale_m_s), float(normalized_velocity[1] * velocity_scale_m_s), 0.0)
            if planar
            else (
                float(normalized_velocity[0] * velocity_scale_m_s),
                float(normalized_velocity[1] * velocity_scale_m_s),
                float(normalized_velocity[2] * velocity_scale_m_s),
            )
        )
        residual = arrival_residual(velocity)
        validate_vec3(residual, "arrival_residual")
        return np.asarray(residual[:2] if planar else residual, dtype=float) / residual_scale_m

    solver_tol = min(
        1e-8 if planar else 1e-13,
        max(1e-14, 1e-3 * (arrival_tolerance_m / residual_scale_m)),
    )

    optimization = least_squares(
        normalized_residual,
        initial,
        method="lm" if planar else "trf",
        max_nfev=max_evaluations,
        xtol=solver_tol,
        ftol=solver_tol,
        gtol=solver_tol,
    )

    velocity: Vec3 = (
        (float(optimization.x[0] * velocity_scale_m_s), float(optimization.x[1] * velocity_scale_m_s), 0.0)
        if planar
        else (
            float(optimization.x[0] * velocity_scale_m_s),
            float(optimization.x[1] * velocity_scale_m_s),
            float(optimization.x[2] * velocity_scale_m_s),
        )
    )
    raw_residual = arrival_residual(velocity)
    validate_vec3(raw_residual, "arrival_residual")
    residual: Vec3 = (float(raw_residual[0]), float(raw_residual[1]), float(raw_residual[2]))
    residual_norm = math.hypot(residual[0], residual[1], residual[2])
    return ShootingResult(
        initial_velocity_m_s=velocity,
        arrival_residual_m=residual,
        residual_norm_m=residual_norm,
        converged=bool(optimization.success and residual_norm <= arrival_tolerance_m),
        evaluations=int(optimization.nfev),
        message=str(optimization.message),
    )