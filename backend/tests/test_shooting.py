import pytest

from app.models.domain import Vec3
from app.physics.shooting import solve_shooting


def test_shooting_corrects_all_three_velocity_components() -> None:
    def residual(velocity: Vec3) -> Vec3:
        return (
            2.0 * velocity[0] - 10.0,
            velocity[1] + 3.0,
            0.5 * velocity[2] - 4.0,
        )

    result = solve_shooting(
        (0.0, 0.0, 0.0),
        residual,
        velocity_scale_m_s=1.0,
        residual_scale_m=1.0,
        arrival_tolerance_m=1e-8,
    )

    assert result.converged
    assert result.initial_velocity_m_s == pytest.approx((5.0, -3.0, 8.0), abs=1e-8)
    assert result.arrival_residual_m == pytest.approx((0.0, 0.0, 0.0), abs=1e-8)
