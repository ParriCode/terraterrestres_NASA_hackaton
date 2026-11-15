"""Objetivo 1 (Marte): catálogo, efemérides escalables y SpatialScenario sin red."""
from datetime import datetime, timezone

import numpy as np
import pytest

from app.mission.config.bodies import CELESTIAL_BODIES
from app.mission.data import ephemeris
from app.mission.data.bodies import load_bodies
from app.mission.data.scenarios import SpatialScenario

DATE = datetime(2026, 11, 15, tzinfo=timezone.utc)
# Posiciones/velocidades sintéticas (centro 500@3), suficientes para la base Tierra–Luna.
STATES = {
    "earth": ((-4.6e6, 0.0, 0.0), (0.0, -12.0, 0.0)),
    "moon": ((3.8e8, 0.0, 0.0), (0.0, 1000.0, 0.0)),
    "sun": ((1.47e11, 1.0e10, 0.0), (-2.0e3, 2.9e4, 0.0)),
    "mars": ((-2.0e11, 1.2e11, 5.0e9), (-1.0e4, -2.2e4, 0.0)),
}


@pytest.fixture
def fake_horizons(monkeypatch):
    calls = []

    def table(body, start, stop, intervals):
        calls.append((body.id, intervals))
        t = np.linspace(0.0, (stop - start).total_seconds(), intervals + 1)
        p0, v = map(np.asarray, STATES[body.id])
        pos = p0 + np.outer(t, v)
        return tuple(t), tuple(map(tuple, pos)), tuple(tuple(v) for _ in t)

    monkeypatch.setattr(ephemeris, "get_body_state_table", table)
    return calls


def test_catalog_has_mars_with_requested_constants():
    mars = load_bodies()["mars"]
    assert mars.mu_m3_s2 == pytest.approx(4.282837e13)
    assert mars.radius_m == pytest.approx(3.3895e6)
    assert next(b for b in CELESTIAL_BODIES if b.id == "mars").horizons_id == "499"


def test_lunar_bodies_unchanged():
    bodies = load_bodies()
    assert bodies["earth"].mu_m3_s2 == 398600435436000.0
    assert bodies["moon"].mu_m3_s2 == 4902800066000.0
    assert bodies["sun"].mu_m3_s2 == 1.3271244004193938e20


@pytest.mark.parametrize("days, step", [(35, 600.0), (50, 600.0), (138, 600.0), (260, 1200.0), (400, 1800.0)])
def test_master_step_keeps_600s_for_lunar_windows_and_scales_for_mars(days, step):
    assert ephemeris._master_step_for(days) == step
    assert days * 86400 / ephemeris._master_step_for(days) <= ephemeris._MAX_MASTER_ROWS


def test_spatial_scenario_default_is_unchanged(fake_horizons):
    scenario = SpatialScenario(DATE, 14 * 86400)
    assert set(scenario.bodies) == {"earth", "moon", "sun"}
    assert scenario.frame == "earth_moon_barycentric_orbital_3d"
    # 14 días a 600 s = 2016 intervalos, como antes.
    assert ("earth", 2016) in fake_horizons


def test_spatial_scenario_with_mars_over_interplanetary_window(fake_horizons):
    duration = 260 * 86400
    scenario = SpatialScenario(DATE, duration, spacing_s=3600.0, include_mars=True)
    assert set(scenario.bodies) == {"earth", "moon", "sun", "mars"}
    mars, sun = scenario.bodies["mars"], scenario.bodies["sun"]
    assert mars.mu_m3_s2 == pytest.approx(4.282837e13)
    # Mismo marco y base para todos: la posición heliocéntrica es r_Marte − r_Sol.
    basis = scenario.basis_icrf
    expected = basis @ (np.asarray(STATES["mars"][0]) - np.asarray(STATES["sun"][0]))
    assert np.allclose(np.subtract(mars.pos(0.0), sun.pos(0.0)), expected)
    assert mars.pos(duration) is not None  # cubre toda la ventana
    assert ("mars", 6240) in fake_horizons  # 260 d / 3600 s


def test_too_fine_spacing_for_long_window_explains_the_fix(fake_horizons):
    with pytest.raises(ValueError, match="spacing_s >= "):
        SpatialScenario(DATE, 260 * 86400, include_mars=True)  # 600 s → 37440 intervalos
