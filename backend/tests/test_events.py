import pytest

from app.models.domain import SpacecraftState
from app.physics.events import is_collision


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ((2.0, 0.0, 0.0), False),  # fuera
        ((1.0, 0.0, 0.0), True),   # justo en la superficie
        ((0.5, 0.0, 0.0), True),   # dentro
        ((0.0, 0.0, 0.0), True),   # centro
    ],
)
def test_is_collision(position, expected):
    state = SpacecraftState(
        position_m=position,
        velocity_m_s=(0.0, 0.0, 0.0),
    )

    assert is_collision(state, (0.0, 0.0, 0.0), 1.0) is expected


@pytest.mark.parametrize("radius", [0.0, -1.0, float("nan"), float("inf")])
def test_is_collision_rejects_invalid_radius(radius):
    state = SpacecraftState((2.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    with pytest.raises(ValueError, match="Invalid body radius"):
        is_collision(state, (0.0, 0.0, 0.0), radius)


def test_is_collision_rejects_non_finite_distance():
    state = SpacecraftState((1e308, 0.0, 0.0), (0.0, 0.0, 0.0))

    with pytest.raises(ValueError, match="Non-finite distance"):
        is_collision(state, (0.0, 0.0, 0.0), 1.0)
