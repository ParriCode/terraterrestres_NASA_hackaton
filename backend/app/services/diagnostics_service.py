"""Resumen y diagnóstico de resultados."""

from __future__ import annotations

import math

from app.models.domain import (
    CelestialBody,
    Diagnostics,
    Event,
    SimulationConfig,
    SimulationResult,
    SimulationStatus,
    TrajectorySample,
    Vec3,
)


def _euclidean_distance_m(pos_a: Vec3, pos_b: Vec3) -> float:
    """Compute the 3D Euclidean distance in meters between two Vec3 coordinates."""
    return math.hypot(
        pos_a[0] - pos_b[0],
        pos_a[1] - pos_b[1],
        pos_a[2] - pos_b[2],
    )


def compute_diagnostics(
    samples: list[TrajectorySample],
    bodies: list[CelestialBody],
) -> Diagnostics:
    """
    Compute the v1 diagnostic summary over the recorded trajectory samples.
    """
    if not samples:
        raise ValueError("Cannot compute diagnostics from an empty trajectory.")
    if samples[0].t_s != 0.0:
        raise ValueError("The first trajectory sample must start at t_s = 0.0.")
    if not bodies:
        raise ValueError("At least one celestial body is required to compute diagnostics.")

    final_time_s = float(samples[-1].t_s)
    steps_completed = len(samples) - 1  # Exclude initial sample at t_s = 0.0

    min_distance_m: dict[str, float] = {}
    min_altitude_m: dict[str, float] = {}

    for body in bodies:
        distances: list[float] = []
        for sample in samples:
            if body.id not in sample.body_positions_m:
                raise ValueError(
                    f"Sample at t_s={sample.t_s} is missing position for body '{body.id}'."
                )
            dist = _euclidean_distance_m(
                sample.spacecraft.position_m,
                sample.body_positions_m[body.id],
            )
            distances.append(dist)

        body_min_dist = min(distances)
        min_distance_m[body.id] = body_min_dist
        min_altitude_m[body.id] = body_min_dist - body.radius_m

    return Diagnostics(
        final_time_s=final_time_s,
        steps_completed=steps_completed,
        min_distance_m=min_distance_m,
        min_altitude_m=min_altitude_m,
    )


def build_simulation_result(
    config: SimulationConfig,
    bodies: list[CelestialBody],
    status: SimulationStatus,
    samples: list[TrajectorySample],
    events: list[Event] | None = None,
) -> SimulationResult:
    """
    Assemble the final SimulationResult with computed diagnostics and
    chronologically ordered events.
    """
    ordered_events = sorted(events or [], key=lambda e: e.t_s)
    diagnostics = compute_diagnostics(samples=samples, bodies=bodies)

    return SimulationResult(
        config=config,
        bodies=list(bodies),
        status=status,
        samples=list(samples),
        events=ordered_events,
        diagnostics=diagnostics,
    )