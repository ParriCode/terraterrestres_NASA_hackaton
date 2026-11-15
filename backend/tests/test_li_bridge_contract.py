"""Pruebas de integración del motor de Li con FastAPI, sin red ni trayectoria NASA ficticia.

Los estados sintéticos prueban el contrato HTTP. NO prueban validación científica.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app
from app.controllers import li_transfer_controller as li_controller


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


def test_li_round_trip_bridge_validates_entry_and_schema(monkeypatch):
    monkeypatch.setattr(li_controller, 'optimize_round_trip_transfer', lambda *a, **k: StubRT())
    resp = TestClient(create_app()).post('/li-transfers/round-trip', json={
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


def test_li_round_trip_rejects_unverified_revolutions(monkeypatch):
    rt = StubRT()
    rt.mode = 'lunar_orbit'
    rt.lunar_stay_s = 3600.0
    monkeypatch.setattr(li_controller, 'optimize_round_trip_transfer', lambda *a, **k: rt)
    resp = TestClient(create_app()).post('/li-transfers/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'lunar_orbit',
        'max_total_duration_s': 12 * 86400, 'lunar_revolutions': 1,
    })
    assert resp.status_code == 200
    assert resp.json()['status'] == 'no_feasible_solution'
    assert 'vueltas' in resp.json()['reasons'][0]


def test_li_round_trip_rejects_outbound_final_velocity(monkeypatch):
    class Outgoing(StubRT):
        def state(self, t):
            state = super().state(t)
            return SimpleNamespace(position_m=state.position_m, velocity_m_s=(10.0, 0.0, 0.0))
    monkeypatch.setattr(li_controller, 'optimize_round_trip_transfer', lambda *a, **k: Outgoing())
    resp = TestClient(create_app()).post('/li-transfers/round-trip', json={
        'date': '2026-11-14T00:00:00Z', 'mode': 'free_return',
    })
    assert resp.status_code == 200
    assert resp.json()['status'] == 'no_feasible_solution'


def test_li_validation_rejects_bad_mode_and_missing_timezone():
    client = TestClient(create_app())
    for body in [
        {'date': '2026-11-14T00:00:00', 'mode': 'free_return'},
        {'date': '2026-11-14T00:00:00Z', 'mode': 'free_return', 'lunar_revolutions': 1},
        {'date': '2026-11-14T00:00:00Z', 'mode': 'not_a_mode'},
    ]:
        resp = client.post('/li-transfers/round-trip', json=body)
        assert resp.status_code == 422, resp.text


def test_lunar_orbit_display_grid_samples_orbit_more_densely():
    from app.controllers.li_transfer_controller import _time_grid
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
