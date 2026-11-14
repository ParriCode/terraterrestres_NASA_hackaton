import pytest

from app.models.domain import SpacecraftState
from app.physics.events import (
    is_collision,
    swept_collision_closest_fraction,
)


def make_state(position):
    return SpacecraftState(
        position_m=position,
        velocity_m_s=(0.0, 0.0, 0.0),
    )


def test_collision_on_surface():
    state = make_state((1.0, 0.0, 0.0))

    assert is_collision(
        state,
        (0.0, 0.0, 0.0),
        1.0,
    )


def test_collision_inside_body():
    state = make_state((0.5, 0.0, 0.0))

    assert is_collision(
        state,
        (0.0, 0.0, 0.0),
        1.0,
    )


def test_no_collision_outside_body():
    state = make_state((2.0, 0.0, 0.0))

    assert not is_collision(
        state,
        (0.0, 0.0, 0.0),
        1.0,
    )


def test_swept_collision_detects_crossing():
    # La nave comienza y termina fuera del planeta,
    # pero atraviesa su esfera durante el desplazamiento.
    fraction = swept_collision_closest_fraction(
        spacecraft_start_m=(-2.0, 0.5, 0.0),
        spacecraft_end_m=(2.0, 0.5, 0.0),
        body_start_m=(0.0, 0.0, 0.0),
        body_end_m=(0.0, 0.0, 0.0),
        body_radius_m=1.0,
    )

    assert fraction is not None
    assert fraction == pytest.approx(0.5)


def test_swept_collision_does_not_detect_miss():
    fraction = swept_collision_closest_fraction(
        spacecraft_start_m=(-2.0, 2.0, 0.0),
        spacecraft_end_m=(2.0, 2.0, 0.0),
        body_start_m=(0.0, 0.0, 0.0),
        body_end_m=(0.0, 0.0, 0.0),
        body_radius_m=1.0,
    )

    assert fraction is None


def test_invalid_radius():
    state = make_state((2.0, 0.0, 0.0))

    with pytest.raises(ValueError):
        is_collision(
            state,
            (0.0, 0.0, 0.0),
            0.0,
        )


def test_non_finite_position():
    state = make_state((float("nan"), 0.0, 0.0))

    with pytest.raises(ValueError):
        is_collision(
            state,
            (0.0, 0.0, 0.0),
            1.0,
        )