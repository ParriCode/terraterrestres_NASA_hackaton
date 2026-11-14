"""Tests for the domain models and validation helpers."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

# Allows running this file directly with `python backend/tests/test_domain.py`
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

from app.models.domain import (
    CelestialBody,
    DEFAULT_UNITS,
    Diagnostics,
    Event,
    EventType,
    REFERENCE_FRAME,
    SCHEMA_VERSION,
    SimulationConfig,
    SimulationResult,
    SimulationStatus,
    SpacecraftState,
    TrajectorySample,
    validate_finite,
    validate_non_empty_str,
    validate_non_negative,
    validate_positive,
    validate_vec3,
)


# --- Fixtures ---

@pytest.fixture
def earth() -> CelestialBody:
    return CelestialBody(
        id="earth",
        name="Earth",
        mu_m3_s2=3.986004418e14,
        radius_m=6_371_000.0,
    )


@pytest.fixture
def moon() -> CelestialBody:
    return CelestialBody(
        id="moon",
        name="Moon",
        mu_m3_s2=4.9048695e12,
        radius_m=1_737_400.0,
    )


@pytest.fixture
def initial_state() -> SpacecraftState:
    return SpacecraftState(
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_m_s=(0.0, 7_500.0, 0.0),
    )


@pytest.fixture
def launch_date() -> datetime:
    return datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def valid_config(initial_state: SpacecraftState, launch_date: datetime) -> SimulationConfig:
    return SimulationConfig(
        scenario_id="earth_moon_circular_v1",
        initial_state=initial_state,
        duration_s=100.0,
        step_s=10.0,
        date=launch_date,
    )


# --- 1. Constants & Enums ---

def test_constants_and_enums() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert REFERENCE_FRAME == "earth_moon_barycentric_inertial"
    assert DEFAULT_UNITS == {
        "length": "m",
        "time": "s",
        "velocity": "m/s",
        "gravitational_parameter": "m^3/s^2",
    }
    assert EventType.COLLISION == "collision"
    assert SimulationStatus.COMPLETED == "completed"
    assert SimulationStatus.COLLISION == "collision"
    assert SimulationStatus.NUMERICAL_ERROR == "numerical_error"


# --- 2. Common Validation Helpers ---

@pytest.mark.parametrize("bad_num", [math.nan, math.inf, -math.inf, True, False, "10"])
def test_validate_finite_rejects_non_finite_or_bool(bad_num: object) -> None:
    with pytest.raises(ValueError):
        validate_finite(bad_num, "test_field")  # type: ignore[arg-type]


def test_validate_positive_and_non_negative() -> None:
    validate_positive(0.001, "pos_field")
    with pytest.raises(ValueError):
        validate_positive(0.0, "pos_field")
    with pytest.raises(ValueError):
        validate_positive(-5.0, "pos_field")

    validate_non_negative(0.0, "non_neg_field")
    validate_non_negative(12.5, "non_neg_field")
    with pytest.raises(ValueError):
        validate_non_negative(-0.001, "non_neg_field")


@pytest.mark.parametrize(
    "bad_vec",
    [
        [1.0, 2.0, 3.0],          # list instead of tuple
        (1.0, 2.0),               # 2 elements
        (1.0, 2.0, 3.0, 4.0),     # 4 elements
        (1.0, math.nan, 0.0),     # NaN component
        (0.0, math.inf, 0.0),     # inf component
        (0.0, 0.0, True),         # bool component
    ],
)
def test_validate_vec3_rejects_invalid_tuples(bad_vec: object) -> None:
    with pytest.raises(ValueError):
        validate_vec3(bad_vec, "vec_field")  # type: ignore[arg-type]


def test_validate_non_empty_str() -> None:
    validate_non_empty_str("earth", "id")
    with pytest.raises(TypeError):
        validate_non_empty_str(None, "id")
    with pytest.raises(TypeError):
        validate_non_empty_str(123, "id")
    with pytest.raises(ValueError):
        validate_non_empty_str("", "id")
    with pytest.raises(ValueError):
        validate_non_empty_str("   ", "id")


# --- 3. Immutability ---

def test_dataclasses_are_frozen(earth: CelestialBody, valid_config: SimulationConfig) -> None:
    with pytest.raises(FrozenInstanceError):
        earth.radius_m = 1.0  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        valid_config.duration_s = 500.0  # type: ignore[misc]


# --- 4. CelestialBody ---

def test_celestial_body_valid_and_invalid(earth: CelestialBody) -> None:
    assert earth.id == "earth"
    assert earth.mu_m3_s2 > 0.0

    with pytest.raises(ValueError):
        CelestialBody(id="", name="Earth", mu_m3_s2=3.986e14, radius_m=6_371_000.0)
    with pytest.raises(ValueError):
        CelestialBody(id="earth", name="   ", mu_m3_s2=3.986e14, radius_m=6_371_000.0)
    with pytest.raises(ValueError):
        CelestialBody(id="earth", name="Earth", mu_m3_s2=0.0, radius_m=6_371_000.0)
    with pytest.raises(ValueError):
        CelestialBody(id="earth", name="Earth", mu_m3_s2=3.986e14, radius_m=-10.0)


# --- 5. SpacecraftState ---

def test_spacecraft_state_valid_and_invalid(initial_state: SpacecraftState) -> None:
    assert initial_state.position_m == (7_000_000.0, 0.0, 0.0)

    with pytest.raises(ValueError):
        SpacecraftState(position_m=(math.nan, 0.0, 0.0), velocity_m_s=(0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        SpacecraftState(position_m=(0.0, 0.0, 0.0), velocity_m_s=(0.0, 1.0))  # type: ignore[arg-type]


# --- 6. SimulationConfig ---

def test_simulation_config_valid_and_invalid(
    valid_config: SimulationConfig,
    initial_state: SpacecraftState,
    launch_date: datetime,
) -> None:
    assert valid_config.step_s == 10.0
    assert valid_config.date == launch_date

    with pytest.raises(ValueError):
        SimulationConfig(
            scenario_id="  ",
            initial_state=initial_state,
            duration_s=100.0,
            step_s=10.0,
            date=launch_date,
        )
    with pytest.raises(TypeError):
        SimulationConfig(
            scenario_id="earth_moon_circular_v1",
            initial_state=((7e6, 0.0, 0.0), (0.0, 7500.0, 0.0)),  # type: ignore[arg-type]
            duration_s=100.0,
            step_s=10.0,
            date=launch_date,
        )
    with pytest.raises(ValueError):
        SimulationConfig(
            scenario_id="earth_moon_circular_v1",
            initial_state=initial_state,
            duration_s=0.0,
            step_s=10.0,
            date=launch_date,
        )
    with pytest.raises(ValueError):
        SimulationConfig(
            scenario_id="earth_moon_circular_v1",
            initial_state=initial_state,
            duration_s=100.0,
            step_s=-5.0,
            date=launch_date,
        )
    with pytest.raises(TypeError):
        SimulationConfig(
            scenario_id="earth_moon_circular_v1",
            initial_state=initial_state,
            duration_s=100.0,
            step_s=10.0,
            date="2026-11-14T12:00:00Z",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="timezone"):
        SimulationConfig(
            scenario_id="earth_moon_circular_v1",
            initial_state=initial_state,
            duration_s=100.0,
            step_s=10.0,
            date=datetime(2026, 11, 14, 12, 0),  # Naive datetime without timezone
        )


# --- 7. TrajectorySample ---

def test_trajectory_sample_valid_and_invalid(initial_state: SpacecraftState) -> None:
    sample = TrajectorySample(
        t_s=0.0,
        spacecraft=initial_state,
        body_positions_m={"earth": (0.0, 0.0, 0.0), "moon": (384_400_000.0, 0.0, 0.0)},
    )
    assert sample.t_s == 0.0

    with pytest.raises(ValueError):
        TrajectorySample(t_s=-1.0, spacecraft=initial_state, body_positions_m={"earth": (0.0, 0.0, 0.0)})
    with pytest.raises(TypeError):
        TrajectorySample(t_s=0.0, spacecraft="not_a_state", body_positions_m={"earth": (0.0, 0.0, 0.0)})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TrajectorySample(t_s=0.0, spacecraft=initial_state, body_positions_m={})
    with pytest.raises(ValueError):
        TrajectorySample(t_s=0.0, spacecraft=initial_state, body_positions_m={"   ": (0.0, 0.0, 0.0)})
    with pytest.raises(ValueError):
        TrajectorySample(t_s=0.0, spacecraft=initial_state, body_positions_m={"earth": (0.0, math.inf, 0.0)})


# --- 8. Event ---

def test_event_valid_and_invalid() -> None:
    event = Event(
        type=EventType.COLLISION,
        t_s=42.5,
        body_id="moon",
        position_m=(382_662_600.0, 0.0, 0.0),
    )
    assert event.type == EventType.COLLISION

    with pytest.raises(TypeError):
        Event(type="collision", t_s=42.5, body_id="moon", position_m=(0.0, 0.0, 0.0))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Event(type=EventType.COLLISION, t_s=-0.1, body_id="moon", position_m=(0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        Event(type=EventType.COLLISION, t_s=10.0, body_id="  ", position_m=(0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        Event(type=EventType.COLLISION, t_s=10.0, body_id="moon", position_m=(0.0, 0.0, math.nan))


# --- 9. Diagnostics ---

def test_diagnostics_valid_and_invalid() -> None:
    diag = Diagnostics(
        final_time_s=100.0,
        steps_completed=10,
        min_distance_m={"earth": 6_370_000.0, "moon": 370_000_000.0},
        min_altitude_m={"earth": -1_000.0, "moon": 368_262_600.0},
    )
    assert diag.min_altitude_m["earth"] == -1_000.0

    with pytest.raises(ValueError):
        Diagnostics(final_time_s=-1.0, steps_completed=0, min_distance_m={}, min_altitude_m={})
    with pytest.raises(ValueError):
        Diagnostics(final_time_s=10.0, steps_completed=-1, min_distance_m={}, min_altitude_m={})
    with pytest.raises(ValueError):
        Diagnostics(final_time_s=10.0, steps_completed=True, min_distance_m={}, min_altitude_m={})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Diagnostics(final_time_s=10.0, steps_completed=1, min_distance_m={"earth": -5.0}, min_altitude_m={})
    with pytest.raises(ValueError):
        Diagnostics(final_time_s=10.0, steps_completed=1, min_distance_m={}, min_altitude_m={"earth": math.nan})


# --- 10. SimulationResult ---

def test_simulation_result_valid_and_invalid(
    earth: CelestialBody,
    valid_config: SimulationConfig,
    initial_state: SpacecraftState,
) -> None:
    s0 = TrajectorySample(t_s=0.0, spacecraft=initial_state, body_positions_m={"earth": (0.0, 0.0, 0.0)})
    s1 = TrajectorySample(t_s=10.0, spacecraft=initial_state, body_positions_m={"earth": (0.0, 0.0, 0.0)})
    diag = Diagnostics(
        final_time_s=10.0,
        steps_completed=1,
        min_distance_m={"earth": 7_000_000.0},
        min_altitude_m={"earth": 629_000.0},
    )

    result = SimulationResult(
        config=valid_config,
        bodies=[earth],
        status=SimulationStatus.COMPLETED,
        samples=[s0, s1],
        events=[],
        diagnostics=diag,
    )
    assert result.schema_version == "1.0"
    assert result.frame == "earth_moon_barycentric_inertial"
    assert result.units == DEFAULT_UNITS
    assert result.units is not DEFAULT_UNITS

    # Invalid status
    with pytest.raises(TypeError):
        SimulationResult(
            config=valid_config,
            bodies=[earth],
            status="completed",  # type: ignore[arg-type]
            samples=[s0, s1],
            events=[],
            diagnostics=diag,
        )

    # Empty samples
    with pytest.raises(ValueError):
        SimulationResult(
            config=valid_config,
            bodies=[earth],
            status=SimulationStatus.COMPLETED,
            samples=[],
            events=[],
            diagnostics=diag,
        )

    # First sample not at t_s = 0.0
    with pytest.raises(ValueError):
        SimulationResult(
            config=valid_config,
            bodies=[earth],
            status=SimulationStatus.COMPLETED,
            samples=[s1],
            events=[],
            diagnostics=diag,
        )

    # Non-increasing sample timestamps
    with pytest.raises(ValueError):
        SimulationResult(
            config=valid_config,
            bodies=[earth],
            status=SimulationStatus.COMPLETED,
            samples=[s0, s1, s1],
            events=[],
            diagnostics=diag,
        )

    # Out-of-order events
    e1 = Event(type=EventType.COLLISION, t_s=10.0, body_id="earth", position_m=(6_371_000.0, 0.0, 0.0))
    e0 = Event(type=EventType.COLLISION, t_s=5.0, body_id="earth", position_m=(6_371_000.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        SimulationResult(
            config=valid_config,
            bodies=[earth],
            status=SimulationStatus.COLLISION,
            samples=[s0, s1],
            events=[e1, e0],
            diagnostics=diag,
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))