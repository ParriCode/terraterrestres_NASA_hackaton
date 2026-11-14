"""Tests for the diagnostics service."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

# Allows running this file directly with `python backend/tests/test_diagnostics_service.py`
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

from app.models.domain import (
    CelestialBody,
    Diagnostics,
    Event,
    EventType,
    SimulationConfig,
    SimulationResult,
    SimulationStatus,
    SpacecraftState,
    TrajectorySample,
)
from app.services.diagnostics_service import (
    _euclidean_distance_m,
    build_simulation_result,
    compute_diagnostics,
)

EARTH_POS = (-4_670_000.0, 0.0, 0.0)
MOON_POS = (379_730_000.0, 0.0, 0.0)


# --- Fixtures and helpers ---

@pytest.fixture
def earth() -> CelestialBody:
    return CelestialBody(id="earth", name="Earth", mu_m3_s2=3.986004418e14, radius_m=6_371_000.0)


@pytest.fixture
def moon() -> CelestialBody:
    return CelestialBody(id="moon", name="Moon", mu_m3_s2=4.9048695e12, radius_m=1_737_400.0)


@pytest.fixture
def config() -> SimulationConfig:
    return SimulationConfig(
        scenario_id="earth_moon_circular_v1",
        initial_state=SpacecraftState(position_m=(2_330_000.0, 0.0, 0.0), velocity_m_s=(0.0, 7_500.0, 0.0)),
        duration_s=100.0,
        step_s=10.0,
        date=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
    )


def make_sample(
    t_s: float,
    spacecraft_pos: tuple[float, float, float],
    earth_pos: tuple[float, float, float] = EARTH_POS,
    moon_pos: tuple[float, float, float] = MOON_POS,
) -> TrajectorySample:
    return TrajectorySample(
        t_s=t_s,
        spacecraft=SpacecraftState(position_m=spacecraft_pos, velocity_m_s=(0.0, 0.0, 0.0)),
        body_positions_m={"earth": earth_pos, "moon": moon_pos},
    )


def at_earth_distance(r_m: float) -> tuple[float, float, float]:
    """Spacecraft position on the +x axis at ``r_m`` meters from Earth's center."""
    return (EARTH_POS[0] + r_m, 0.0, 0.0)


# --- _euclidean_distance_m ---

@pytest.mark.parametrize(
    "a, b, expected",
    [
        ((0.0, 0.0, 0.0), (3.0, 4.0, 0.0), 5.0),
        ((1.0, 2.0, 3.0), (3.0, 4.0, 4.0), 3.0),
        ((5.0, 5.0, 5.0), (5.0, 5.0, 5.0), 0.0),
        ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0), math.sqrt(12.0)),
    ],
    ids=["3-4-5", "3d_(2,2,1)", "same_point", "negative_coords"],
)
def test_euclidean_distance(a: tuple[float, float, float], b: tuple[float, float, float], expected: float) -> None:
    assert _euclidean_distance_m(a, b) == pytest.approx(expected)
    assert _euclidean_distance_m(b, a) == pytest.approx(expected)


# --- compute_diagnostics: values ---

def test_minimum_is_neither_first_nor_last_sample(earth: CelestialBody, moon: CelestialBody) -> None:
    samples = [
        make_sample(0.0, at_earth_distance(7_000_000.0)),
        make_sample(10.0, at_earth_distance(6_500_000.0)),
        make_sample(20.0, at_earth_distance(7_000_000.0)),
    ]
    diag = compute_diagnostics(samples, [earth, moon])

    assert diag.min_distance_m["earth"] == pytest.approx(6_500_000.0)
    assert diag.min_altitude_m["earth"] == pytest.approx(6_500_000.0 - earth.radius_m)
    assert diag.final_time_s == 20.0
    assert diag.steps_completed == 2


def test_altitude_is_negative_when_inside_body(earth: CelestialBody, moon: CelestialBody) -> None:
    samples = [
        make_sample(0.0, at_earth_distance(7_000_000.0)),
        make_sample(10.0, at_earth_distance(6_370_000.0)),
    ]
    diag = compute_diagnostics(samples, [earth, moon])
    assert diag.min_altitude_m["earth"] == pytest.approx(-1_000.0)


def test_altitude_is_zero_on_the_surface(earth: CelestialBody, moon: CelestialBody) -> None:
    samples = [make_sample(0.0, at_earth_distance(earth.radius_m))]
    diag = compute_diagnostics(samples, [earth, moon])
    assert diag.min_altitude_m["earth"] == pytest.approx(0.0, abs=1e-6)


def test_moving_bodies_have_independent_minima(earth: CelestialBody, moon: CelestialBody) -> None:
    origin = (0.0, 0.0, 0.0)
    samples = [
        make_sample(0.0, origin, earth_pos=(10.0, 0.0, 0.0), moon_pos=(100.0, 0.0, 0.0)),
        make_sample(10.0, origin, earth_pos=(20.0, 0.0, 0.0), moon_pos=(30.0, 40.0, 0.0)),
        make_sample(20.0, origin, earth_pos=(30.0, 0.0, 0.0), moon_pos=(300.0, 0.0, 0.0)),
    ]
    diag = compute_diagnostics(samples, [earth, moon])

    assert diag.min_distance_m["earth"] == pytest.approx(10.0)
    assert diag.min_distance_m["moon"] == pytest.approx(50.0)
    assert diag.min_altitude_m["moon"] == pytest.approx(50.0 - moon.radius_m)


def test_diagnostics_keys_follow_bodies(earth: CelestialBody, moon: CelestialBody) -> None:
    samples = [make_sample(0.0, at_earth_distance(7_000_000.0))]
    diag = compute_diagnostics(samples, [earth, moon])
    assert set(diag.min_distance_m) == {"earth", "moon"}
    assert set(diag.min_altitude_m) == {"earth", "moon"}

    diag_earth_only = compute_diagnostics(samples, [earth])
    assert set(diag_earth_only.min_distance_m) == {"earth"}


def test_single_sample_has_zero_steps(earth: CelestialBody) -> None:
    diag = compute_diagnostics([make_sample(0.0, at_earth_distance(7_000_000.0))], [earth])
    assert diag.steps_completed == 0
    assert diag.final_time_s == 0.0


# --- compute_diagnostics: errors ---

def test_rejects_empty_samples(earth: CelestialBody) -> None:
    with pytest.raises(ValueError, match="empty trajectory"):
        compute_diagnostics([], [earth])


def test_rejects_first_sample_not_at_zero(earth: CelestialBody) -> None:
    with pytest.raises(ValueError, match="t_s = 0.0"):
        compute_diagnostics([make_sample(5.0, at_earth_distance(7e6))], [earth])


def test_rejects_empty_bodies() -> None:
    with pytest.raises(ValueError, match="At least one celestial body"):
        compute_diagnostics([make_sample(0.0, at_earth_distance(7e6))], [])


def test_missing_body_error_mentions_body_and_time(earth: CelestialBody) -> None:
    mars = CelestialBody(id="mars", name="Mars", mu_m3_s2=4.28e13, radius_m=3_389_500.0)
    samples = [make_sample(0.0, at_earth_distance(7e6)), make_sample(10.0, at_earth_distance(7e6))]
    with pytest.raises(ValueError, match=r"t_s=0\.0.*'mars'"):
        compute_diagnostics(samples, [earth, mars])


# --- build_simulation_result ---

def make_build_inputs(config: SimulationConfig, earth: CelestialBody, moon: CelestialBody) -> dict:
    return {
        "config": config,
        "bodies": [earth, moon],
        "status": SimulationStatus.COMPLETED,
        "samples": [
            make_sample(0.0, at_earth_distance(7_000_000.0)),
            make_sample(10.0, at_earth_distance(6_800_000.0)),
            make_sample(20.0, at_earth_distance(7_000_000.0)),
        ],
    }


def test_build_result_computes_diagnostics_and_passes_data_through(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    inputs = make_build_inputs(config, earth, moon)
    result = build_simulation_result(**inputs)

    assert isinstance(result, SimulationResult)
    assert result.config is config
    assert result.status == SimulationStatus.COMPLETED
    assert result.bodies == [earth, moon]
    assert result.samples == inputs["samples"]
    assert result.events == []
    assert result.diagnostics == compute_diagnostics(inputs["samples"], inputs["bodies"])
    assert result.diagnostics.min_distance_m["earth"] == pytest.approx(6_800_000.0)


def test_build_result_sorts_events_chronologically(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    late = Event(type=EventType.COLLISION, t_s=15.0, body_id="earth", position_m=(0.0, 0.0, 0.0))
    early = Event(type=EventType.COLLISION, t_s=5.0, body_id="earth", position_m=(1.0, 0.0, 0.0))
    result = build_simulation_result(
        **{**make_build_inputs(config, earth, moon), "status": SimulationStatus.COLLISION},
        events=[late, early],
    )
    assert [e.t_s for e in result.events] == [5.0, 15.0]


def test_build_result_sort_is_stable_for_equal_timestamps(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    first = Event(type=EventType.COLLISION, t_s=10.0, body_id="earth", position_m=(1.0, 0.0, 0.0))
    second = Event(type=EventType.COLLISION, t_s=10.0, body_id="moon", position_m=(2.0, 0.0, 0.0))
    result = build_simulation_result(
        **{**make_build_inputs(config, earth, moon), "status": SimulationStatus.COLLISION},
        events=[first, second],
    )
    assert result.events == [first, second]


def test_build_result_without_events_gives_empty_list(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    inputs = make_build_inputs(config, earth, moon)
    assert build_simulation_result(**inputs).events == []
    assert build_simulation_result(**inputs, events=[]).events == []
    assert build_simulation_result(**inputs, events=None).events == []


def test_build_result_is_isolated_from_later_input_changes(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    inputs = make_build_inputs(config, earth, moon)
    result = build_simulation_result(**inputs)

    inputs["samples"].clear()
    inputs["bodies"].clear()
    assert len(result.samples) == 3
    assert len(result.bodies) == 2


def test_build_result_propagates_validation_errors(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    inputs = make_build_inputs(config, earth, moon)

    with pytest.raises(ValueError, match="empty trajectory"):
        build_simulation_result(**{**inputs, "samples": []})

    s0, s1, _ = inputs["samples"]
    with pytest.raises(ValueError, match="strictly increasing"):
        build_simulation_result(**{**inputs, "samples": [s0, s1, s1]})


def test_build_result_is_json_serializable(
    config: SimulationConfig, earth: CelestialBody, moon: CelestialBody
) -> None:
    result = build_simulation_result(**make_build_inputs(config, earth, moon))
    payload = json.loads(json.dumps(dataclasses.asdict(result), default=str))

    assert payload["status"] == "completed"
    assert payload["config"]["date"] == "2026-11-14 12:00:00+00:00"
    assert payload["diagnostics"]["steps_completed"] == 2
    assert payload["diagnostics"]["final_time_s"] == 20.0
    assert set(payload["diagnostics"]["min_distance_m"]) == {"earth", "moon"}
    assert len(payload["samples"]) == 3
    assert isinstance(result.diagnostics, Diagnostics)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))