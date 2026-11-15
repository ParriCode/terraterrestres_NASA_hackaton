"""Regresión: la búsqueda debe converger con estancia lunar temporal fija.

Las efemérides de este test son sintéticas: no se consideran una
validación de las trayectorias de NASA/JPL Horizons.
"""
from datetime import datetime, timezone

import numpy as np

from app.mission.data.bodies import load_bodies
from app.services.mission_optimizer import optimize_round_trip_transfer


def test_lunar_orbit_six_hours_and_return_converges_with_synthetic_ephemerides(monkeypatch):
    catalog = load_bodies()
    mu_earth = catalog["earth"].mu_m3_s2
    mu_moon = catalog["moon"].mu_m3_s2
    separation_m = 384_400_000.0
    angular_speed = np.sqrt((mu_earth + mu_moon) / separation_m**3)

    def states(body, start, stop, intervals):
        times = np.linspace(0.0, (stop - start).total_seconds(), intervals + 1)
        if body.id == "sun":
            positions = np.tile((1.495978707e11, 2.1e10, 0.0), (len(times), 1))
            velocities = np.zeros_like(positions)
        else:
            radius = (
                -separation_m * mu_moon / (mu_earth + mu_moon)
                if body.id == "earth"
                else separation_m * mu_earth / (mu_earth + mu_moon)
            )
            angle = angular_speed * times + 0.05
            positions = np.stack(
                (radius * np.cos(angle), radius * np.sin(angle), np.zeros_like(times)), axis=1
            )
            velocities = np.stack(
                (-radius * angular_speed * np.sin(angle),
                 radius * angular_speed * np.cos(angle), np.zeros_like(times)), axis=1
            )
        return times, positions, velocities

    monkeypatch.setattr("app.mission.data.ephemeris.get_body_state_table", states)
    stay_seconds = 6.0 * 3600.0
    result = optimize_round_trip_transfer(
        datetime(2026, 11, 15, tzinfo=timezone.utc),
        mode="lunar_orbit",
        max_total_duration_s=14.0 * 86400.0,
        lunar_periapsis_alt_m=150_000.0,
        lunar_stay_s=stay_seconds,
        reentry_alt_m=120_000.0,
    )

    assert result.mode == "lunar_orbit"
    assert abs(result.lunar_stay_s - stay_seconds) < 1e-4
    assert len(result._segments) == 3
    assert result.total_duration_s <= 14.0 * 86400.0
    assert abs(result.earth_reentry_altitude_m - 120_000.0) <= 40_000.0
    earth = result.scenario.bodies["earth"]
    state = result.state(result.total_duration_s)
    r_rel = np.asarray(state.position_m) - np.asarray(earth.pos(result.total_duration_s))
    v_rel = np.asarray(state.velocity_m_s) - np.asarray(earth.speed(result.total_duration_s))
    assert float(np.dot(r_rel, v_rel)) < 0.0  # llega acercándose a la Tierra
