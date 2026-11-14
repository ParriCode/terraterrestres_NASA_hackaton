"""Regresiones offline: evitar integración dentro de planetas y explicar errores."""

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.services.transfer_service as service
from app.main import create_app
from app.physics.propagation import propagate_planar


class FixedEarth:
    id = "earth"
    radius_m = 6_371_000.0
    mu_m3_s2 = 3.986004418e14

    def pos(self, t):
        return (0.0, 0.0, 0.0)


def test_shooting_stops_early_on_planet_collision():
    """Una candidata que cae hacia la Tierra no llega a la singularidad central."""
    earth = FixedEarth()
    scenario = SimpleNamespace(get_bodies=lambda: [earth])
    result = propagate_planar(
        scenario,
        (earth.radius_m + 100_000.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        0.0, 3600.0,
        events=False,  # Durante shooting también se comprueban impactos.
    )
    assert result.status == 1
    assert result.t[-1] < 3600.0
    assert len(result.t_events[0]) == 1


def test_optimizer_marks_search_incomplete_when_budget_expires(monkeypatch):
    service.optimize_transfer.cache_clear()
    clock = [0.0]

    class FakeBody:
        radius_m = 1.0
        def __init__(self, x):
            self.x = x
        def pos(self, t):
            return (self.x, 0.0, 0.0)

    class FakeScenario:
        def __init__(self, date, duration_s, *, spacing_s):
            self.bodies = {"earth": FakeBody(0.0), "moon": FakeBody(100.0)}

    def fake_F(*args, **kwargs):
        clock[0] += 1.0
        return SimpleNamespace(launch_energy_j=1.0, path_length_m=1.0)

    monkeypatch.setattr(service, "PlanarScenario", FakeScenario)
    monkeypatch.setattr(service, "F", fake_F)
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])

    result = service.optimize_transfer(
        datetime(2026, 11, 14, tzinfo=timezone.utc),
        86400.0,
        time_budget_s=0.5,
        coarse_step_deg=90,
    )
    assert result.valid_candidates == 1
    assert not result.search_complete
    service.optimize_transfer.cache_clear()


def test_repeated_identical_request_uses_calculation_cache(monkeypatch):
    service.optimize_transfer.cache_clear()
    calls = [0]

    class FakeBody:
        radius_m = 1.0
        def __init__(self, x):
            self.x = x
        def pos(self, t):
            return (self.x, 0.0, 0.0)

    class FakeScenario:
        def __init__(self, date, duration_s, *, spacing_s):
            calls[0] += 1
            self.bodies = {"earth": FakeBody(0.0), "moon": FakeBody(100.0)}

    def fake_F(*args, **kwargs):
        return SimpleNamespace(launch_energy_j=1.0, path_length_m=1.0)

    monkeypatch.setattr(service, "PlanarScenario", FakeScenario)
    monkeypatch.setattr(service, "F", fake_F)
    date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    a = service.optimize_transfer(date, 86400.0, coarse_step_deg=90)
    b = service.optimize_transfer(date, 86400.0, coarse_step_deg=90)
    assert a is b
    assert calls[0] == 1
    service.optimize_transfer.cache_clear()


def test_no_candidate_422_is_descriptive(monkeypatch):
    def no_result(*args, **kwargs):
        raise service.TransferNotFoundError("No se encontró ningún candidato válido")

    monkeypatch.setattr('app.controllers.transfer_controller.optimize_transfer', no_result)
    response = TestClient(create_app(simulation_mode='mock')).post('/transfers/optimize', json={
        "date": "2026-11-14T00:00:00Z",
        "duration_s": 86400.0,
        "objective": "energia",
    })
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'no_valid_transfer'
    assert 'duration' not in response.json()['detail']
