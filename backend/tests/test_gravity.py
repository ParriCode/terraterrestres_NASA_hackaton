import pytest

from app.physics.gravity import GravityError, gravitational_acceleration
from app.models.domain import CelestialBody


def test_single_body_acceleration_points_towards_body(earth_like_body):
    acceleration = gravitational_acceleration(
        spacecraft_position_m=(2.0, 0.0, 0.0),
        body_positions_m={"earth": (0.0, 0.0, 0.0)},
        bodies=[earth_like_body],
    )

    # a = -mu * r_vec / |r|^3; mu=10 y distancia=2 => ax=-2.5.
    assert acceleration[0] == pytest.approx(-2.5)
    assert acceleration[1] == pytest.approx(0.0)
    assert acceleration[2] == pytest.approx(0.0)


def test_inverse_square_law(earth_like_body):
    near = gravitational_acceleration(
        (2.0, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)}, [earth_like_body]
    )
    far = gravitational_acceleration(
        (4.0, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)}, [earth_like_body]
    )

    assert abs(near[0] / far[0]) == pytest.approx(4.0)


def test_superposition_of_two_bodies_cancels_symmetrically(earth_like_body):
    second_body = CelestialBody(
        id="moon",
        name="Moon",
        mu_m3_s2=10.0,
        radius_m=0.5,
    )

    acceleration = gravitational_acceleration(
        spacecraft_position_m=(2.0, 0.0, 0.0),
        body_positions_m={
            "earth": (0.0, 0.0, 0.0),
            "moon": (4.0, 0.0, 0.0),
        },
        bodies=[earth_like_body, second_body],
    )

    assert acceleration == pytest.approx((0.0, 0.0, 0.0))


def test_missing_body_position_raises_gravity_error(earth_like_body):
    with pytest.raises(GravityError, match="Missing position"):
        gravitational_acceleration(
            (2.0, 0.0, 0.0), {}, [earth_like_body]
        )


def test_spacecraft_at_body_center_raises_gravity_error(earth_like_body):
    with pytest.raises(GravityError, match="center"):
        gravitational_acceleration(
            (0.0, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)}, [earth_like_body]
        )


def test_spacecraft_inside_body_raises_gravity_error(earth_like_body):
    with pytest.raises(GravityError, match="inside"):
        gravitational_acceleration(
            (0.5, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)}, [earth_like_body]
        )


def test_spacecraft_exactly_on_surface_has_finite_gravity(earth_like_body):
    """La gravedad en la superficie es finita; el evento de impacto se detecta aparte."""
    acceleration = gravitational_acceleration(
        (1.0, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)}, [earth_like_body]
    )

    assert acceleration == pytest.approx((-10.0, 0.0, 0.0))


def test_non_finite_distance_raises_gravity_error(earth_like_body):
    with pytest.raises(GravityError, match="Non-finite distance"):
        gravitational_acceleration(
            (float("inf"), 0.0, 0.0),
            {"earth": (0.0, 0.0, 0.0)},
            [earth_like_body],
        )


def test_non_finite_result_raises_gravity_error():
    body = CelestialBody(
        id="earth",
        name="Earth",
        mu_m3_s2=float("inf"),
        radius_m=1.0,
    )
    with pytest.raises(GravityError, match="Invalid acceleration"):
        gravitational_acceleration(
            (2.0, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)}, [body]
        )
