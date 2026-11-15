"""Pruebas del optimizador de transferencias Tierra→Luna."""
from datetime import datetime, timezone

import numpy as np
import pytest

from app.mission.data.bodies import load_bodies
from app.mission.data.scenarios import PlanarScenario
from app.services.mission_optimizer import (
    Candidate,
    NoFeasibleTransfer,
    build_tradeoff_curve,
    deduplicate_candidates,
    optimize_transfer,
    screen,
)


@pytest.fixture
def circular_ephemeris(monkeypatch):
    catalog = load_bodies()
    mu_t, mu_l = (catalog[k].mu_m3_s2 for k in ("earth", "moon"))
    distance = 384400000.0
    omega = np.sqrt((mu_t + mu_l) / distance**3)

    def table(body, start, stop, intervals):
        times = np.linspace(0, (stop - start).total_seconds(), intervals + 1)
        radius = -distance * mu_l / (mu_t + mu_l) if body.id == "earth" else distance * mu_t / (mu_t + mu_l)
        positions = np.column_stack((radius * np.cos(omega * times),
                                     radius * np.sin(omega * times), np.zeros_like(times)))
        velocities = np.column_stack((-radius * omega * np.sin(omega * times),
                                      radius * omega * np.cos(omega * times), np.zeros_like(times)))
        return times, positions, velocities

    monkeypatch.setattr("app.mission.data.ephemeris.get_body_state_table", table)


def test_screen_orders_candidates_and_respects_domain(circular_ephemeris):
    date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    max_duration_s = 6 * 86400.0
    scenario = PlanarScenario(date, max_duration_s)
    candidates = screen(scenario, parking_alt_m=200_000.0, max_duration_s=max_duration_s)

    assert len(candidates) > 0
    assert all(2.5 * 86400.0 <= c.duration_s <= max_duration_s for c in candidates)
    dvs = [c.estimated_total_delta_v_m_s for c in candidates]
    assert dvs == sorted(dvs)

    curve = build_tradeoff_curve(candidates)
    assert [p.duration_s for p in curve] == sorted(p.duration_s for p in curve)


def test_deduplicate_candidates_keeps_distinct_regions():
    cands = [
        Candidate(5 * 86400, 240.0, 270.0, True, 3100, 900, 2540, 5640),
        Candidate(5 * 86400, 252.0, 270.0, True, 3110, 910, 2545, 5655),  # mismo entorno
        Candidate(5.5 * 86400, 240.0, 300.0, True, 3120, 915, 2548, 5668),  # mismo entorno
        Candidate(3.5 * 86400, 264.0, 270.0, True, 3150, 1200, 2660, 5810),  # distinta región temporal
    ]
    selected = deduplicate_candidates(cands, limit=4)
    assert len(selected) == 2
    assert selected[0].duration_s == 5 * 86400
    assert selected[1].duration_s == 3.5 * 86400


def test_optimize_transfer_within_max_duration_and_matches_lambert_tolerance(circular_ephemeris):
    date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    max_duration_s = 10 * 86400.0
    opt = optimize_transfer(date, max_duration_s, parking_alt_m=200_000.0)

    assert opt.transfer.t1_s <= max_duration_s
    assert opt.transfer.t1_s >= opt.min_duration_s
    assert opt.transfer.arrival_error_m < 1000.0
    assert len(opt.tradeoff) > 0

    # La estimación Lambert de 2 cuerpos debe acercarse al Δv validado por DOP853 (tolerancia 15%).
    est_dv = opt.best_candidate.estimated_total_delta_v_m_s
    actual_dv = opt.transfer.total_delta_v_m_s
    assert abs(est_dv - actual_dv) / actual_dv < 0.15


def test_feasible_set_monotonicity_3_days_vs_10_days(circular_ephemeris):
    date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    opt_3d = optimize_transfer(date, 3 * 86400.0, parking_alt_m=200_000.0)
    opt_10d = optimize_transfer(date, 10 * 86400.0, parking_alt_m=200_000.0)

    assert opt_3d.transfer.t1_s <= 3 * 86400.0
    assert opt_10d.transfer.t1_s <= 10 * 86400.0
    # Un máximo de 3 días es un subconjunto del de 10 días: no puede lograr menor Δv.
    assert opt_10d.transfer.total_delta_v_m_s <= opt_3d.transfer.total_delta_v_m_s + 1.0


def test_one_day_limit_outside_search_domain_raises_no_feasible(circular_ephemeris):
    date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    with pytest.raises(NoFeasibleTransfer) as exc_info:
        optimize_transfer(date, 1 * 86400.0, parking_alt_m=200_000.0)
    assert exc_info.value.tradeoff == []
    assert any("dominio" in r.lower() for r in exc_info.value.reasons)