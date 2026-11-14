"""Creación de los cuerpos, nave y simulación."""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import math

Vec3 = tuple[float, float, float]

SCHEMA_VERSION = "1.0"
REFERENCE_FRAME = "earth_moon_barycentric_inertial"
DEFAULT_UNITS: dict[str, str] = {
    "length": "m",
    "time": "s",
    "velocity": "m/s",
    "gravitational_parameter": "m^3/s^2",
}


class EventType(str, Enum):
    COLLISION = "collision"


class SimulationStatus(str, Enum):
    COMPLETED = "completed"
    COLLISION = "collision"
    NUMERICAL_ERROR = "numerical_error"


# --- Funciones de validación comunes ---

def validate_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Field '{field_name}' must be a finite number (received: {value}).")


def validate_positive(value: float, field_name: str) -> None:
    validate_finite(value, field_name)
    if value <= 0.0:
        raise ValueError(f"Field '{field_name}' must be strictly positive (received: {value}).")


def validate_non_negative(value: float, field_name: str) -> None:
    validate_finite(value, field_name)
    if value < 0.0:
        raise ValueError(f"Field '{field_name}' cannot be negative (received: {value}).")


def validate_vec3(vec: Vec3, field_name: str) -> None:
    if not isinstance(vec, tuple) or len(vec) != 3:
        raise ValueError(f"Field '{field_name}' must be a 3-element Vec3 tuple (received: {vec}).")
    for idx, component in enumerate(vec):
        validate_finite(component, f"{field_name}[{idx}]")


# --- Estructuras del dominio ---

# Guarda un cuerpo celeste con su id, nombre, valor gravitatorio y radio
@dataclass(frozen=True)
class CelestialBody:
    id: str
    name: str
    mu_m3_s2: float
    radius_m: float

    # Variable validations
    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("The 'id' cannot be empty.")
        if not self.name or not self.name.strip():
            raise ValueError("The 'name' cannot be empty.")
        validate_positive(self.mu_m3_s2, "mu_m3_s2")
        validate_positive(self.radius_m, "radius_m")


# Un instante de la nave con su posición y velocidad
@dataclass(frozen=True)
class SpacecraftState:
    position_m: Vec3
    velocity_m_s: Vec3

    # Variable validations
    def __post_init__(self) -> None:
        validate_vec3(self.position_m, "position_m")
        validate_vec3(self.velocity_m_s, "velocity_m_s")


# Lo necesario para lanzar una simulación, id, estado inicial de la nave, tiempo de simulación
# y salto de tiempo de integración
@dataclass(frozen=True)
class SimulationConfig:
    scenario_id: str
    initial_state: SpacecraftState
    duration_s: float
    step_s: float
    date: datetime

    # Variable validations
    def __post_init__(self) -> None:
        if not self.scenario_id or not self.scenario_id.strip():
            raise ValueError("The 'scenario_id' cannot be empty.")
        if not isinstance(self.initial_state, SpacecraftState):
            raise TypeError("'initial_state' must be an instance of SpacecraftState.")
        validate_positive(self.duration_s, "duration_s")
        validate_positive(self.step_s, "step_s")
        if not isinstance(self.date, datetime):
            raise TypeError("'date' must be a datetime instance.")
        if self.date.utcoffset() is None:
            raise ValueError("'date' must include a timezone.")


# Define una misión con nombre, cuerpo de salida y llegada y fecha
@dataclass(frozen=True)
class Simulation:
    name: str
    origin_body: CelestialBody
    destination_body: CelestialBody
    date: datetime


    # Variable validations
#    def __post_init__(self) -> None:
#        if not self.name or not self.name.strip():
#            raise ValueError("The 'name' cannot be empty.")
#        if not isinstance(self.origin_body, CelestialBody):
#            raise TypeError("'origin_body' must be an instance of CelestialBody.")
#        if not isinstance(self.destination_body, CelestialBody):
#            raise TypeError("'destination_body' must be an instance of CelestialBody.")
#        if self.origin_body.id == self.destination_body.id:
#            raise ValueError("'origin_body' and 'destination_body' must be different bodies.")
#        if not isinstance(self.date, datetime):
#            raise TypeError("'date' must be a valid datetime instance.")


# Une en un tiempo el estado de la nave y las posiciones de los cuerpos
@dataclass(frozen=True)
class TrajectorySample:
    t_s: float
    spacecraft: SpacecraftState
    body_positions_m: dict[str, Vec3]

    # Variable validations
    def __post_init__(self) -> None:
        validate_non_negative(self.t_s, "t_s")
        if not isinstance(self.spacecraft, SpacecraftState):
            raise TypeError("'spacecraft' must be an instance of SpacecraftState.")
        if not self.body_positions_m:
            raise ValueError("'body_positions_m' must contain the positions of the bodies.")
        for body_id, pos in self.body_positions_m.items():
            if not body_id:
                raise ValueError("The keys of 'body_positions_m' cannot be empty.")
            validate_vec3(pos, f"body_positions_m['{body_id}']")


# Registro de incidentes
@dataclass(frozen=True)
class Event:
    type: EventType
    t_s: float
    body_id: str
    position_m: Vec3

    # Variable validations
    def __post_init__(self) -> None:
        if not isinstance(self.type, EventType):
            raise TypeError("'type' must be a valid EventType.")
        validate_non_negative(self.t_s, "t_s")
        if not self.body_id or not self.body_id.strip():
            raise ValueError("'body_id' cannot be empty.")
        validate_vec3(self.position_m, "position_m")


# Resumen de diagnostico de pasos completados, tiempo y distancias
@dataclass(frozen=True)
class Diagnostics:
    final_time_s: float
    steps_completed: int
    min_distance_m: dict[str, float]
    min_altitude_m: dict[str, float]

    # Variable validations
    def __post_init__(self) -> None:
        validate_non_negative(self.final_time_s, "final_time_s")
        if isinstance(self.steps_completed, bool) or not isinstance(self.steps_completed, int) or self.steps_completed < 0:
            raise ValueError("'steps_completed' must be an integer greater than or equal to 0.")
        for body_id, dist in self.min_distance_m.items():
            validate_non_negative(dist, f"min_distance_m['{body_id}']")
        for body_id, alt in self.min_altitude_m.items():
            validate_finite(alt, f"min_altitude_m['{body_id}']")


# Resultado final
@dataclass(frozen=True)
class SimulationResult:
    config: SimulationConfig
    bodies: list[CelestialBody]
    status: SimulationStatus
    samples: list[TrajectorySample]
    events: list[Event]
    diagnostics: Diagnostics
    schema_version: str = SCHEMA_VERSION
    frame: str = REFERENCE_FRAME
    units: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_UNITS))

    # Variable validations
    def __post_init__(self) -> None:
        if not isinstance(self.status, SimulationStatus):
            raise TypeError("'status' must be a valid SimulationStatus.")
        if not self.samples:
            raise ValueError("'samples' must contain at least the initial sample at t_s = 0.")
        if self.samples[0].t_s != 0.0:
            raise ValueError("The first sample must have t_s = 0.0.")
        for i in range(1, len(self.samples)):
            if self.samples[i].t_s <= self.samples[i - 1].t_s:
                raise ValueError("The sample times must be strictly increasing.")
        for i in range(1, len(self.events)):
            if self.events[i].t_s < self.events[i - 1].t_s:
                raise ValueError("The events must be in chronological order.")
