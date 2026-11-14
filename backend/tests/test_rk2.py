import math
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.models.domain import (
    SimulationStatus,
    SpacecraftState,
)
from app.physics.rk2 import (
    integrate,
    rk2_step,
)


@dataclass
class FakeBody:
    """Cuerpo sencillo para las pruebas."""

    id: str = "planet"
    radius_m: float = 1.0
    mu_m3_s2: float = 0.0
    fail_after_s: float | None = None
    queried_times: list[float] = field(default_factory=list)

    def pos(self, time_s: float):
        if (
            self.fail_after_s is not None
            and time_s > self.fail_after_s
        ):
            raise ValueError("Fake ephemeris error")

        self.queried_times.append(time_s)

        return (0.0, 0.0, 0.0)


class FakeMovingBody(FakeBody):

    def pos(self, time_s: float):
        self.queried_times.append(time_s)

        return (10.0 + time_s, 0.0, 0.0)


class FakeScenario:
    def __init__(self, bodies=None):
        bodies = bodies or []

        self.bodies = {
            body.id: body
            for body in bodies
        }

    def get_bodies(self):
        return list(self.bodies.values())


def make_state(
    position=(0.0, 0.0, 0.0),
    velocity=(0.0, 0.0, 0.0),
):
    return SpacecraftState(
        position_m=position,
        velocity_m_s=velocity,
    )


def make_config(
    initial_state,
    duration_s,
    step_s,
):
    return SimpleNamespace(
        initial_state=initial_state,
        duration_s=duration_s,
        step_s=step_s,
    )


def test_rk2_constant_velocity():
    scenario = FakeScenario()

    initial_state = make_state(
        position=(1.0, 2.0, 3.0),
        velocity=(2.0, 0.0, -1.0),
    )

    result = rk2_step(
        t_s=0.0,
        state=initial_state,
        step_s=2.0,
        scenario=scenario,
    )

    assert result.position_m == pytest.approx(
        (5.0, 2.0, 1.0)
    )

    assert result.velocity_m_s == pytest.approx(
        (2.0, 0.0, -1.0)
    )


def test_rk2_queries_midpoint_ephemeris():
    body = FakeMovingBody(
        id="planet",
        radius_m=0.1,
        mu_m3_s2=1.0,
    )

    scenario = FakeScenario([body])

    rk2_step(
        t_s=0.0,
        state=make_state(),
        step_s=1.0,
        scenario=scenario,
    )

    assert 0.0 in body.queried_times
    assert 0.5 in body.queried_times


def test_rk2_rejects_zero_step():
    with pytest.raises(ValueError):
        rk2_step(
            t_s=0.0,
            state=make_state(),
            step_s=0.0,
            scenario=FakeScenario(),
        )


def test_rk2_rejects_negative_time():
    with pytest.raises(ValueError):
        rk2_step(
            t_s=-1.0,
            state=make_state(),
            step_s=1.0,
            scenario=FakeScenario(),
        )


def test_integrate_zero_duration():
    config = make_config(
        initial_state=make_state(
            position=(10.0, 0.0, 0.0),
            velocity=(1.0, 0.0, 0.0),
        ),
        duration_s=0.0,
        step_s=1.0,
    )

    samples, events, status = integrate(
        config,
        FakeScenario(),
    )

    assert status == SimulationStatus.COMPLETED
    assert len(samples) == 1
    assert samples[0].t_s == 0.0
    assert events == []


def test_integrate_final_partial_step():
    config = make_config(
        initial_state=make_state(
            position=(0.0, 0.0, 0.0),
            velocity=(1.0, 0.0, 0.0),
        ),
        duration_s=1.1,
        step_s=0.5,
    )

    samples, events, status = integrate(
        config,
        FakeScenario(),
    )

    assert status == SimulationStatus.COMPLETED
    assert events == []

    times = [sample.t_s for sample in samples]

    assert times == pytest.approx(
        [0.0, 0.5, 1.0, 1.1]
    )

    assert samples[-1].spacecraft.position_m == pytest.approx(
        (1.1, 0.0, 0.0)
    )


def test_integrate_initial_collision():
    body = FakeBody(
        id="planet",
        radius_m=1.0,
        mu_m3_s2=0.0,
    )

    scenario = FakeScenario([body])

    config = make_config(
        initial_state=make_state(
            position=(1.0, 0.0, 0.0),
        ),
        duration_s=10.0,
        step_s=1.0,
    )

    samples, events, status = integrate(
        config,
        scenario,
    )

    assert status == SimulationStatus.COLLISION
    assert len(samples) == 1
    assert len(events) == 1

    assert events[0].body_id == "planet"
    assert events[0].t_s == 0.0


def test_integrate_detects_crossing_between_endpoints():
    body = FakeBody(
        id="planet",
        radius_m=1.0,
        mu_m3_s2=0.0,
    )

    scenario = FakeScenario([body])

    # La nave empieza y termina fuera de la esfera.
    # Sin comprobación del segmento, el impacto se perdería.
    config = make_config(
        initial_state=make_state(
            position=(-2.0, 0.5, 0.0),
            velocity=(4.0, 0.0, 0.0),
        ),
        duration_s=1.0,
        step_s=1.0,
    )

    samples, events, status = integrate(
        config,
        scenario,
    )

    assert status == SimulationStatus.COLLISION
    assert len(events) == 1

    event = events[0]

    assert event.body_id == "planet"

    # Para una trayectoria recta y una esfera unitaria,
    # el primer contacto está en x = -sqrt(1 - 0.5²).
    expected_time = (
        2.0 - math.sqrt(0.75)
    ) / 4.0

    assert event.t_s == pytest.approx(
        expected_time,
        abs=2e-6,
    )

    # La muestra final debe corresponder al evento.
    assert samples[-1].t_s == event.t_s

    # La nave debe estar sobre la superficie.
    impact_distance = math.dist(
        samples[-1].spacecraft.position_m,
        (0.0, 0.0, 0.0),
    )

    assert impact_distance == pytest.approx(
        1.0,
        abs=1e-5,
    )


def test_integrate_keeps_valid_samples_on_error():
    body = FakeBody(
        id="planet",
        radius_m=0.1,
        mu_m3_s2=0.0,
        fail_after_s=0.6,
    )

    scenario = FakeScenario([body])

    config = make_config(
        initial_state=make_state(
            position=(10.0, 0.0, 0.0),
            velocity=(1.0, 0.0, 0.0),
        ),
        duration_s=1.0,
        step_s=0.5,
    )

    samples, events, status = integrate(
        config,
        scenario,
    )

    assert status == SimulationStatus.NUMERICAL_ERROR

    # Debe conservar las muestras de los pasos válidos.
    assert [sample.t_s for sample in samples] == pytest.approx(
        [0.0, 0.5]
    )

    assert events == []


def test_integrate_rejects_invalid_step():
    config = make_config(
        initial_state=make_state(),
        duration_s=10.0,
        step_s=0.0,
    )

    with pytest.raises(ValueError):
        integrate(
            config,
            FakeScenario(),
        )