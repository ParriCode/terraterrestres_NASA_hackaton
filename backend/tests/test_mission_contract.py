"""Pruebas de integración del optimizador de misiones con FastAPI, sin red ni trayectoria NASA ficticia.

Los estados sintéticos prueban el contrato HTTP. NO prueban validación científica.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.controllers import mission_controller as mission_controller


class StubBody:
    def __init__(self, name, radius):
        self.name = name
        self.radius_m = radius
        self.mu_m3_s2 = 3.986e14

    def pos(self, t):
        return (0.0, 0.0, 0.0) if self.name == 'Earth' else (384_400_000.0, 0.0, 0.0)

    def speed(self, t):
        return (0.0, 0.0, 0.0)


class StubDenseSolution:
    def sol(self, times):
        ts = np.asarray(times)
        x = 6_491_000.0 + (7 * 86400.0 - ts) * 10
        return np.vstack((x, ts * 0, ts * 0, ts * 0 - 10, ts * 0, ts * 0))


class StubRT:
    mode = 'free_return'
    outbound_duration_s = 3 * 86400.0
    lunar_stay_s = 0.0
    inbound_duration_s = 4 * 86400.0
    total_duration_s = 7 * 86400.0
    tli_delta_v_m_s = 3250.0
    loi_delta_v_m_s = 0.0
    tei_delta_v_m_s = 0.0
    total_delta_v_m_s = 3250.0
    min_lunar_altitude_m = 150_000.0
    earth_reentry_altitude_m = 120_000.0
    scenario = SimpleNamespace(
        frame='earth_moon_barycentric_orbital_3d',
        basis_icrf=np.eye(3),
        bodies={
            'earth': StubBody('Earth', 6_371_000.0),
            'moon': StubBody('Moon', 1_737_000.0),
            'sun': StubBody('Sun', 696_000_000.0),
        },
    )
    _segments = ((0.0, 7 * 86400.0, StubDenseSolution()),)

    def state(self, t):
        if t == self.total_duration_s:
            p = (6_491_000.0, 0.0, 0.0)
        else:
            p = (6_491_000.0 + (self.total_duration_s - t) * 10, 0.0, 0.0)
        return SimpleNamespace(position_m=p, velocity_m_s=(-10.0, 0.0, 0.0))

    def pos(self, t):
        return self.state(t).position_m

    def speed(self, t):
        return self.state(t).velocity_m_s


def test_mission_round_trip_bridge_validates_entry_and_schema(monkeypatch):
    monkeypatch.setattr(mission_controller, 'optimize_round_trip_transfer', lambda *a, **k: StubRT())
    resp = TestClient(create_app()).post('/missions/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'free_return',
        'max_total_duration_s': 12 * 86400, 'mass_kg': 1000, 'samples': 30,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['status'] == 'ok'
    assert data['earth_entry_validated'] is True
    assert data['earth_entry_inbound'] is True
    assert data['earth_entry_relative_speed_m_s'] == 10
    assert data['earth_reentry_altitude_m'] == 120000
    assert data['total_delta_v_m_s'] == 3250
    assert len(data['samples']) == 30
    assert data['samples'][0]['t_s'] == 0
    assert data['samples'][-1]['t_s'] == 7 * 86400


def test_mission_round_trip_rejects_unverified_revolutions(monkeypatch):
    rt = StubRT()
    rt.mode = 'lunar_orbit'
    rt.lunar_stay_s = 3600.0
    monkeypatch.setattr(mission_controller, 'optimize_round_trip_transfer', lambda *a, **k: rt)
    resp = TestClient(create_app()).post('/missions/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'lunar_orbit',
        'max_total_duration_s': 12 * 86400, 'lunar_revolutions': 1,
    })
    assert resp.status_code == 200
    assert resp.json()['status'] == 'no_feasible_solution'
    assert 'vueltas' in resp.json()['reasons'][0]


def test_mission_round_trip_rejects_outbound_final_velocity(monkeypatch):
    class Outgoing(StubRT):
        def state(self, t):
            state = super().state(t)
            return SimpleNamespace(position_m=state.position_m, velocity_m_s=(10.0, 0.0, 0.0))
    monkeypatch.setattr(mission_controller, 'optimize_round_trip_transfer', lambda *a, **k: Outgoing())
    resp = TestClient(create_app()).post('/missions/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'free_return',
    })
    assert resp.status_code == 200
    assert resp.json()['status'] == 'no_feasible_solution'


def test_mission_validation_rejects_bad_mode_and_missing_timezone():
    client = TestClient(create_app())
    for body in [
        {'date': '2026-11-14T00:00:00', 'mode': 'free_return'},
        {'date': '2026-11-14T00:00:00Z', 'mode': 'free_return', 'lunar_revolutions': 1},
        {'date': '2026-11-14T00:00:00Z', 'mode': 'not_a_mode'},
    ]:
        resp = client.post('/missions/round-trip', json=body)
        assert resp.status_code == 422, resp.text


def test_lunar_orbit_display_grid_samples_orbit_more_densely():
    from app.controllers.mission_controller import _time_grid
    rt = StubRT()
    rt.mode = 'lunar_orbit'
    rt.outbound_duration_s = 3 * 86400.0
    rt.lunar_stay_s = 8_000.0
    rt._segments = (
        (0.0, 3 * 86400.0, StubDenseSolution()),
        (3 * 86400.0, 3 * 86400.0 + 8000, StubDenseSolution()),
        (3 * 86400.0 + 8000, 7 * 86400.0, StubDenseSolution()),
    )
    ts = _time_grid(rt, 7 * 86400.0, 300)
    assert len(ts) == 300
    assert np.all(np.diff(ts) > 0)
    assert np.count_nonzero((ts > 3 * 86400.0) & (ts < 3 * 86400.0 + 8_000.0)) >= 80


def test_lunar_orbit_request_accepts_five_revolutions_and_validates_them(monkeypatch):
    """La cantidad indicada se usa al programar la estancia y verificar las vueltas."""
    import math

    moon = StubRT.scenario.bodies['moon']
    radius = moon.radius_m + 150_000.0
    period = 2 * math.pi * math.sqrt(radius ** 3 / moon.mu_m3_s2)
    rt = StubRT()
    rt.mode = 'lunar_orbit'
    rt.outbound_duration_s = 3 * 86400.0
    rt.lunar_stay_s = 5 * period
    rt.total_duration_s = 7 * 86400.0
    rt.inbound_duration_s = rt.total_duration_s - rt.outbound_duration_s - rt.lunar_stay_s
    rt._segments = ((0, rt.total_duration_s, StubDenseSolution()),)

    def state(t):
        if rt.outbound_duration_s <= t <= rt.outbound_duration_s + rt.lunar_stay_s:
            phi = 5 * 2 * math.pi * (t - rt.outbound_duration_s) / rt.lunar_stay_s
            omega = 5 * 2 * math.pi / rt.lunar_stay_s
            return SimpleNamespace(
                position_m=(384_400_000.0 + radius * math.cos(phi), radius * math.sin(phi), 0.0),
                velocity_m_s=(-radius * omega * math.sin(phi), radius * omega * math.cos(phi), 0.0),
            )
        return StubRT.state(rt, t)

    rt.state = state
    rt.pos = lambda t: rt.state(t).position_m
    rt.speed = lambda t: rt.state(t).velocity_m_s

    captured = {}

    def fake_optimizer(*args, **kwargs):
        captured.update(kwargs)
        return rt

    monkeypatch.setattr(mission_controller, 'load_bodies', lambda: {'moon': moon})
    monkeypatch.setattr(mission_controller, 'optimize_round_trip_transfer', fake_optimizer)
    res = TestClient(create_app()).post('/missions/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'lunar_orbit',
        'max_total_duration_s': 12 * 86400, 'lunar_revolutions': 5,
        'samples': 900,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['status'] == 'ok', data
    assert captured['lunar_stay_s'] == pytest.approx(5 * period)
    assert data['actual_lunar_revolutions'] == pytest.approx(5, abs=0.03)
    assert len(data['samples']) == 900


def test_lunar_orbit_rejects_invalid_revolution_counts():
    client = TestClient(create_app())
    for n in (0, 101, -3, 1.5, True):
        response = client.post('/missions/round-trip', json={
            'date': '2026-11-14T00:00:00Z', 'mode': 'lunar_orbit',
            'lunar_revolutions': n,
        })
        assert response.status_code == 422, (n, response.text)


def test_lunar_orbit_rejects_impossible_duration_before_solver(monkeypatch):
    called = False

    def fake_optimizer(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError('No debe llamarse al optimizador')

    monkeypatch.setattr(mission_controller, 'optimize_round_trip_transfer', fake_optimizer)
    response = TestClient(create_app()).post('/missions/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'lunar_orbit',
        'max_total_duration_s': 6 * 86400, 'lunar_revolutions': 100,
    })
    assert response.status_code == 200
    assert response.json()['status'] == 'no_feasible_solution'
    assert not called


def test_lunar_orbit_dense_grid_supports_many_revolutions():
    from app.controllers.mission_controller import _time_grid
    rt = StubRT()
    rt.mode = 'lunar_orbit'
    rt.outbound_duration_s = 3 * 86400.0
    rt.lunar_stay_s = 30 * 2 * 3600.0
    rt._segments = (
        (0.0, rt.outbound_duration_s, StubDenseSolution()),
        (rt.outbound_duration_s, rt.outbound_duration_s + rt.lunar_stay_s, StubDenseSolution()),
        (rt.outbound_duration_s + rt.lunar_stay_s, 9 * 86400.0, StubDenseSolution()),
    )
    ts = _time_grid(rt, 9 * 86400.0, 900)
    assert len(ts) == 900
    assert np.all(np.diff(ts) > 0)
    assert np.count_nonzero((ts > rt.outbound_duration_s) & (ts < rt.outbound_duration_s + rt.lunar_stay_s)) >= 400
