"""Solar selection, NASA frame, two-body physics and API regressions without network."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.data.scenarios import SolarPlanarScenario
from app.data.bodies import load_bodies
from app.main import create_app
from app.physics.propagation import propagate_planar

DATE = datetime(2026, 11, 15, tzinfo=timezone.utc)


def test_scenario_requests_only_selected_bodies_in_same_frame(monkeypatch):
    calls = []
    def table(body, start, stop, intervals, center):
        calls.append((body.id, center))
        t = np.linspace(0, (stop-start).total_seconds(), intervals+1)
        p = np.tile([1e11 if body.id == 'mars' else 2e11, 3e10, 4e9], (len(t), 1))
        return t, p, np.zeros_like(p)
    monkeypatch.setattr('app.data.ephemeris.get_body_state_table', table)
    s = SolarPlanarScenario(DATE, 200*86400, 'mars', 'jupiter')
    assert calls == [('mars', '500@0'), ('jupiter', '500@0')]
    assert set(s.bodies) == {'mars', 'jupiter'}
    assert s.bodies['mars'].pos(0)[2] == 0
    assert s.bodies['mars'].pos(0)[1] == pytest.approx(np.dot([1e11, 3e10, 4e9], s.basis_icrf[1]))


def test_only_two_accelerations_with_arbitrary_ids():
    def body(id, x, mu):
        return SimpleNamespace(id=id, radius_m=1., mu_m3_s2=mu, pos=lambda t: (x, 0., 0.))
    bodies = [body('mars', 0., 1e6), body('jupiter', 10000., 2e6)]
    scenario = SimpleNamespace(origin_id='mars', get_bodies=lambda: bodies)
    result = propagate_planar(scenario, (2000., 0., 0.), (0., 0., 0.), 0., .001)
    expected = -1e6/2000**2 + 2e6/8000**2
    assert result.y[2, -1] / .001 == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize('payload', [
    {'origin_id': 'earth', 'destination_id': 'earth'},
    {'origin_id': 'invented', 'destination_id': 'mars'},
    {'origin_id': 'earth', 'destination_id': 'mars', 'duration_s': -1},
])
def test_invalid_pair_rejected_before_network(payload):
    response = TestClient(create_app()).post('/transfers/solar', json={'date': DATE.isoformat(), **payload})
    assert response.status_code == 422


def test_nasa_failure_does_not_fabricate_positions(monkeypatch):
    from app.data.ephemeris import EphemerisError
    def fail(*args, **kwargs): raise EphemerisError('NASA unavailable')
    monkeypatch.setattr('app.data.ephemeris._fetch_state', fail)
    response = TestClient(create_app()).get('/ephemeris/solar', params={'date': DATE.isoformat()})
    assert response.status_code == 502
    assert 'body_positions_m' not in response.json()


def test_catalog_covers_solar_system():
    catalog = load_bodies(Path(__file__).parents[1] / 'app/data/solar_bodies.json')
    assert set(catalog) == {'sun','mercury','venus','earth','moon','mars','jupiter','saturn','uranus','neptune'}
    assert catalog['mars'].mu_m3_s2 == pytest.approx(42828.375662e9)


def test_solar_endpoint_returns_selected_pair_and_validated_trajectory(monkeypatch):
    from app.models.domain import CelestialBody
    from app.data.scenarios import PlanarScenarioBody
    from app.services.transfer_service import optimize_transfer
    optimize_transfer.cache_clear()
    duration = 10000.
    times = np.linspace(0, duration, 101)
    bodies = {}
    for key, x in [('mars', 0.), ('venus', 1e6)]:
        body = CelestialBody(id=key, name=key, radius_m=100., mu_m3_s2=1e6)
        positions = np.tile([x, 0., 0.], (len(times), 1))
        bodies[key] = PlanarScenarioBody(body, DATE, times, positions, np.zeros_like(positions))
    scenario = SimpleNamespace(date=DATE, duration_s=duration, origin_id='mars', destination_id='venus',
        bodies=bodies, basis_icrf=np.array([[1.,0.,0.],[0.,1.,0.]]), get_bodies=lambda: list(bodies.values()))
    monkeypatch.setattr('app.services.transfer_service.SolarPlanarScenario', lambda *args: scenario)
    response = TestClient(create_app()).post('/transfers/solar', json={
        'date':DATE.isoformat(), 'duration_s':duration, 'origin_id':'mars', 'destination_id':'venus', 'samples':10})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['gravity_body_ids'] == ['mars', 'venus']
    assert set(result['bodies']) == {'mars', 'venus'}
    assert set(result['samples'][0]['body_positions_m']) == {'mars', 'venus'}
    assert result['frame'] == 'ssb_ecliptic_j2000_projected'
    assert result['arrival_error_m'] < 1000
    assert result['samples'][-1]['t_s'] == duration
    optimize_transfer.cache_clear()
