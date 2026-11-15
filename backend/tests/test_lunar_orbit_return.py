"""Pruebas offline: modelo propulsado Luna y regreso a la interfaz terrestre."""
from datetime import datetime, timezone
from types import SimpleNamespace
import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.services.lunar_mission_service as lunar
from app.main import create_app
from app.services.transfer_service import TransferNotFoundError


class FixedBody:
    def __init__(self, id, name, mu, radius, position):
        self.id = id
        self.name = name
        self.mu_m3_s2 = mu
        self.radius_m = radius
        self.position = position

    def pos(self, t):
        return (*self.position, 0.0)

    def speed(self, t):
        return (0.0, 0.0, 0.0)

    def pos_array(self, times):
        return np.repeat(np.array([[*self.position, 0.0]]), len(times), axis=0)


class FixedScenario:
    def __init__(self, date, duration_s, spacing_s=3600):
        self.duration_s = duration_s
        self.date = date
        self.basis_icrf = np.array([[1, 0, 0], [0, 1, 0]], dtype=float)
        self.bodies = {
            'earth': FixedBody('earth', 'Tierra', 3.986004418e14, 6_371_000.0, (0.0, 0.0)),
            'moon': FixedBody('moon', 'Luna', 4.9048695e12, 1_737_000.0, (384_400_000.0, 0.0)),
        }

    def get_bodies(self):
        return list(self.bodies.values())


def fake_outbound(date, duration_s, **kwargs):
    """Solo prueba el montaje. La ida es un fixture rectilíneo NO científico."""
    scenario = FixedScenario(date, duration_s)
    x0 = scenario.bodies['earth'].radius_m
    x1 = 384_400_000.0 - scenario.bodies['moon'].radius_m
    vx = (x1 - x0) / duration_s

    def state(t):
        x = x0 + vx * np.asarray(t)
        v = np.zeros_like(x) + vx
        z = np.zeros_like(x)
        return np.stack((x, z, v, z))

    transfer = SimpleNamespace(
        scenario=scenario, t1_s=duration_s, _solution=SimpleNamespace(sol=state),
        initial_velocity_m_s=(vx, 0., 0.), launch_speed_m_s=vx,
        launch_energy_j=0.5 * kwargs['mass_kg'] * vx**2,
    )
    return SimpleNamespace(transfer=transfer, arrival_angle_deg=0.0)


def test_insertion_requires_inbound_and_changes_only_velocity():
    s = FixedScenario(datetime(2026, 11, 15, tzinfo=timezone.utc), 86400)
    r = s.bodies['moon'].radius_m + 100_000
    y = np.array([384_400_000 - r, 0, 1400.0, 1000.0])
    inserted, dv = lunar.lunar_orbit_injection(s, 0, y, r)
    assert np.array_equal(inserted[:2], y[:2])
    assert dv > 0
    assert math.isclose(np.linalg.norm(inserted[2:]), math.sqrt(s.bodies['moon'].mu_m3_s2 / r), rel_tol=1e-10)
    with pytest.raises(TransferNotFoundError, match='aproximando'):
        lunar.lunar_orbit_injection(s, 0, np.array([*y[:2], -1400., 1000.]), r)


def test_complete_lunar_orbit_return_with_synthetic_fixed_bodies(monkeypatch):
    """Propaga realmente la órbita y la vuelta; NO valida JPL ni trayectorias reales."""
    monkeypatch.setattr(lunar, 'PlanarScenario', FixedScenario)
    monkeypatch.setattr(lunar, 'optimize_transfer', fake_outbound)
    result = lunar.design_lunar_orbit_return(
        datetime(2026, 11, 15, tzinfo=timezone.utc), 10 * 86400,
        mass_kg=1000., objective='energia', samples=350,
        time_budget_s=40,
    )
    assert result['mission_mode'] == 'lunar_orbit_return'
    assert result['lunar_orbit']['verified_return'] is True
    assert len(result['maneuvers']) == 2
    assert result['maneuvers'][0]['delta_v_m_s'] > 0
    assert result['maneuvers'][1]['delta_v_m_s'] > 0
    ts = [v['t_s'] for v in result['samples']]
    # La duración indicada es un límite, no una fecha exacta de llegada.
    assert ts[0] == 0 and 0 < ts[-1] <= 10 * 86400
    assert ts[-1] == pytest.approx(result['duration_s'])
    assert result['requested_duration_s'] == 10 * 86400
    assert result['lunar_orbit']['return_arrival_t_s'] == pytest.approx(ts[-1])
    assert all(a < b for a, b in zip(ts, ts[1:]))
    last = result['samples'][-1]
    earth_position = np.array(last['body_positions_m']['earth'][:2])
    entry_radius = lunar._entry_radius_m(FixedScenario(datetime(2026, 11, 15, tzinfo=timezone.utc), 10 * 86400))
    assert np.linalg.norm(np.array(last['position_m'][:2]) - earth_position) == pytest.approx(entry_radius, abs=500)
    assert result['earth_entry']['altitude_km'] == 120
    assert result['earth_entry']['inbound'] is True
    assert result['earth_entry']['validated'] is True
    assert result['earth_entry']['landing_simulated'] is False
    assert result['return_interface_radius_m'] == pytest.approx(entry_radius)


def test_earth_entry_uses_actual_body_radius():
    scenario = FixedScenario(datetime(2026, 11, 15, tzinfo=timezone.utc), 86400)
    scenario.bodies['earth'].radius_m = 6_380_000.0
    assert lunar._entry_radius_m(scenario) == pytest.approx(6_500_000.0)


def test_api_rejects_invalid_or_no_solution(monkeypatch):
    client = TestClient(create_app())
    data = {
        'date': '2026-11-15T12:00:00Z', 'duration_s': 10 * 86400,
        'mass_kg': 1000, 'objective': 'energia', 'samples': 300,
    }
    r = client.post('/transfers/lunar-orbit-return', json={**data, 'orbit_altitude_km': 1})
    assert r.status_code == 422
    def no_candidate(*args, **kwargs):
        raise TransferNotFoundError('sin candidato')
    monkeypatch.setattr('app.controllers.transfer_controller.design_lunar_orbit_return', no_candidate)
    r = client.post('/transfers/lunar-orbit-return', json=data)
    assert r.status_code == 422
    assert r.json()['detail']['code'] == 'no_valid_lunar_orbit_return'


def test_api_mission_mode_is_real(monkeypatch):
    client = TestClient(create_app(simulation_mode='mock'))
    monkeypatch.setattr('app.controllers.transfer_controller.design_lunar_orbit_return', lambda *a, **kw: {'ok': True})
    r = client.post('/transfers/lunar-orbit-return', json={
        'date': '2026-11-15T12:00:00Z', 'duration_s': 10 * 86400,
        'mass_kg': 1000, 'objective': 'energia', 'samples': 300,
    })
    assert r.status_code == 200 and r.headers['X-Simulation-Mode'] == 'real'


def test_return_sphere_is_first_inbound_crossing_not_fixed_final_day():
    """Valida la parada por evento usando dinámica gravitatoria sintética."""
    from app.physics.propagation import propagate_planar
    scenario = FixedScenario(datetime(2026, 11, 15, tzinfo=timezone.utc), 10 * 86400)
    solution = propagate_planar(
        scenario,
        (250_000_000., 0.), (-3500., 0.),
        0., 10 * 86400,
        events=True, stop_at_earth_radius_m=100_000_000.,
        dense_output=True, rtol=1e-10, atol=1e-6,
    )
    assert solution.success
    assert len(solution.t_events[-1]) == 1
    assert 0 < solution.t[-1] < 10 * 86400
    assert np.linalg.norm(solution.y[:2, -1]) == pytest.approx(100_000_000., abs=1.)
    assert solution.y[0, -1] * solution.y[2, -1] + solution.y[1, -1] * solution.y[3, -1] < 0
    assert not any(len(hits) for hits in solution.t_events[:-1])


def test_return_sphere_rejects_invalid_radius_or_initial_position():
    from app.physics.propagation import propagate_planar
    scenario = FixedScenario(datetime(2026, 11, 15, tzinfo=timezone.utc), 10 * 86400)
    with pytest.raises(ValueError, match='mayor'):
        propagate_planar(scenario, (250_000_000, 0), (-3500, 0), 0, 10000,
                         stop_at_earth_radius_m=2_000_000)
    with pytest.raises(ValueError, match='fuera'):
        propagate_planar(scenario, (90_000_000, 0), (-3500, 0), 0, 10000,
                         stop_at_earth_radius_m=100_000_000)
