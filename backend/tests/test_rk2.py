import math

import pytest

from app.models.domain import SpacecraftState
import app.physics.rk2 as rk2_module
from app.physics.rk2 import rk2_step, vec_add, vec_scale


class FakeScenario:
    def __init__(self):
        self.bodies = {}


def test_vec_add():
    assert vec_add((1.0, 2.0, 3.0), (4.0, -2.0, 1.0)) == (5.0, 0.0, 4.0)


def test_vec_scale():
    assert vec_scale((1.0, -2.0, 3.0), 2.5) == (2.5, -5.0, 7.5)


def test_rk2_midpoint_step(monkeypatch):
    """Con derivada v'=a constante, RK2 devuelve el avance esperado."""
    calls = []

    def fake_derivative(t_s, state, scenario, bodies):
        calls.append(t_s)
        return state.velocity_m_s, (0.0, 2.0, 0.0)

    monkeypatch.setattr(rk2_module, "state_derivative", fake_derivative)

    initial = SpacecraftState(
        position_m=(1.0, 2.0, 3.0),
        velocity_m_s=(4.0, 5.0, 6.0),
    )
    scenario = FakeScenario()

    result = rk2_step(0.0, initial, 2.0, scenario)

    assert calls == [0.0, 1.0]
    assert result.position_m == pytest.approx((9.0, 16.0, 15.0))
    assert result.velocity_m_s == pytest.approx((4.0, 9.0, 6.0))
    assert initial.position_m == (1.0, 2.0, 3.0)
    assert initial.velocity_m_s == (4.0, 5.0, 6.0)


def test_rk2_queries_derivative_at_start_and_midpoint(monkeypatch):
    times = []

    def fake_derivative(t_s, state, scenario, bodies):
        times.append(t_s)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    monkeypatch.setattr(rk2_module, "state_derivative", fake_derivative)
    state = SpacecraftState((10.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    rk2_step(5.0, state, 4.0, FakeScenario())

    assert times == [5.0, 7.0]


@pytest.mark.parametrize("step_s", [0.0, -1.0, float("nan"), float("inf")])
def test_rk2_rejects_invalid_step(step_s):
    state = SpacecraftState((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))

    with pytest.raises(ValueError):
        rk2_step(0.0, state, step_s, FakeScenario())


def test_rk2_queries_moving_body_at_start_and_midpoint(earth_like_body):
    """La dinámica debe consultar el escenario en ambos instantes de RK2."""
    class MovingBodyScenario:
        bodies = {"earth": earth_like_body}

        def __init__(self):
            self.times = []

        def get_body_pos(self, body, time_s):
            self.times.append(time_s)
            # El cuerpo se desplaza para verificar que cada instante se consulta.
            return (time_s, 0.0, 0.0)

    scenario = MovingBodyScenario()
    state = SpacecraftState(
        position_m=(10.0, 0.0, 0.0),
        velocity_m_s=(0.0, 1.0, 0.0),
    )

    result = rk2_step(5.0, state, 4.0, scenario)

    assert scenario.times == [5.0, 7.0]
    assert all(math.isfinite(value) for value in result.position_m)
    assert all(math.isfinite(value) for value in result.velocity_m_s)
