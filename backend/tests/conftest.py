import pytest

from app.models.domain import CelestialBody, SpacecraftState


@pytest.fixture
def earth_like_body() -> CelestialBody:
    """Cuerpo artificial con parámetros sencillos para cálculos verificables."""
    return CelestialBody(
        id="earth",
        name="Earth",
        mu_m3_s2=10.0,
        radius_m=1.0,
    )


@pytest.fixture
def initial_state() -> SpacecraftState:
    return SpacecraftState(
        position_m=(2.0, 0.0, 0.0),
        velocity_m_s=(0.0, 1.0, 0.0),
    )
