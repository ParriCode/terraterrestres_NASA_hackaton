import pytest
from datetime import datetime, timezone

from app.models.domain import SpacecraftState, SimulationConfig
from app.data.scenarios import Scenario
from app.physics.dynamics import state_derivative


def make_scenario(monkeypatch, body, state):
    monkeypatch.setattr('app.data.scenarios.load_bodies', lambda: {body.id: body})
    return Scenario(SimulationConfig('demo', state, 60., 1., datetime(2026, 11, 14, tzinfo=timezone.utc)))


def test_state_derivative_returns_velocity_and_gravity(monkeypatch, earth_like_body, initial_state):
    scenario = make_scenario(monkeypatch, earth_like_body, initial_state)
    calls = []
    def position(body, instant):
        calls.append((body.id, (instant - scenario.config.date).total_seconds()))
        return (0., 0., 0.)
    monkeypatch.setattr('app.data.scenarios.get_body_time_pos', position)

    position_derivative, velocity_derivative = state_derivative(
        t_s=12.0,
        state=initial_state,
        scenario=scenario,
    )

    assert position_derivative == initial_state.velocity_m_s
    assert velocity_derivative == (-2.5, 0.0, 0.0)
    assert calls == [("earth", 12.0)]
    assert scenario.bodies['earth'].mu_m3_s2 == earth_like_body.mu_m3_s2
    assert scenario.bodies['earth'].radius_m == earth_like_body.radius_m


def test_state_derivative_uses_body_ids_as_position_dictionary_keys(monkeypatch, earth_like_body):
    state = SpacecraftState(
        position_m=(0.0, 2.0, 0.0),
        velocity_m_s=(1.0, 2.0, 3.0),
    )
    scenario = make_scenario(monkeypatch, earth_like_body, state)
    monkeypatch.setattr('app.data.scenarios.get_body_time_pos', lambda *args: (0., 0., 0.))

    _, acceleration = state_derivative(
        3.0, state, scenario
    )

    assert acceleration == pytest.approx((0.0, -2.5, 0.0))
