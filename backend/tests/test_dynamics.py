import pytest

from app.models.domain import SpacecraftState
from app.physics.dynamics import state_derivative


class FakeScenario:
    def __init__(self, positions_by_body_id):
        self.positions_by_body_id = positions_by_body_id
        self.calls = []

    def get_body_pos(self, body, time_s):
        self.calls.append((body.id, time_s))
        return self.positions_by_body_id[body.id]


def test_state_derivative_returns_velocity_and_gravity(earth_like_body, initial_state):
    scenario = FakeScenario({"earth": (0.0, 0.0, 0.0)})

    position_derivative, velocity_derivative = state_derivative(
        t_s=12.0,
        state=initial_state,
        scenario=scenario,
        bodies=[earth_like_body],
    )

    assert position_derivative == initial_state.velocity_m_s
    assert velocity_derivative == (-2.5, 0.0, 0.0)
    assert scenario.calls == [("earth", 12.0)]


def test_state_derivative_uses_body_ids_as_position_dictionary_keys(earth_like_body):
    scenario = FakeScenario({"earth": (0.0, 0.0, 0.0)})
    state = SpacecraftState(
        position_m=(0.0, 2.0, 0.0),
        velocity_m_s=(1.0, 2.0, 3.0),
    )

    _, acceleration = state_derivative(
        3.0, state, scenario, [earth_like_body]
    )

    assert acceleration == pytest.approx((0.0, -2.5, 0.0))
