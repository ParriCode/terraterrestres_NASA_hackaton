from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from app.li_engine.models.domain import Vec3, validate_positive, validate_vec3

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
    """Ajusta la velocidad para anular el error de posición final."""
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

    optimization = least_squares(
        normalized_residual,
        initial,
        method="lm" if planar else "trf",
        max_nfev=max_evaluations,
        xtol=1e-7,
        ftol=1e-7,
        gtol=1e-7,
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
        converged=bool(optimization.status >= 0 and residual_norm <= arrival_tolerance_m),
        evaluations=int(optimization.nfev),
        message=str(optimization.message),
    )