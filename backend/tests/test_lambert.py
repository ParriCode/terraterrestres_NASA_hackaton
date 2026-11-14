import math

import pytest

from app.physics.lambert import LambertError, solve_lambert


def test_lambert_finds_quarter_circular_orbit_in_xy_plane() -> None:
    solution = solve_lambert(
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        math.pi / 2.0,
        1.0,
        tolerance_s=1e-10,
    )

    assert solution.departure_velocity_m_s == pytest.approx((0.0, 1.0, 0.0), abs=1e-7)
    assert solution.arrival_velocity_m_s == pytest.approx((-1.0, 0.0, 0.0), abs=1e-7)


def test_lambert_works_in_an_arbitrary_3d_plane() -> None:
    solution = solve_lambert(
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        math.pi / 2.0,
        1.0,
        plane_normal=(0.0, -1.0, 0.0),
        tolerance_s=1e-10,
    )

    assert solution.departure_velocity_m_s == pytest.approx((0.0, 0.0, 1.0), abs=1e-7)
    assert solution.arrival_velocity_m_s == pytest.approx((-1.0, 0.0, 0.0), abs=1e-7)


def test_lambert_rejects_collinear_positions() -> None:
    with pytest.raises(LambertError, match="colineales"):
        solve_lambert((1.0, 0.0, 0.0), (2.0, 0.0, 0.0), 1.0, 1.0)
