from __future__ import annotations

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
    "masa" : "kg",
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
        raise ValueError(f"El campo '{field_name}' debe ser un número finito (recibido: {value}).")


def validate_positive(value: float, field_name: str) -> None:
    validate_finite(value, field_name)
    if value <= 0.0:
        raise ValueError(f"El campo '{field_name}' debe ser estrictamente positivo (recibido: {value}).")


def validate_non_negative(value: float, field_name: str) -> None:
    validate_finite(value, field_name)
    if value < 0.0:
        raise ValueError(f"El campo '{field_name}' no puede ser negativo (recibido: {value}).")


def validate_vec3(vec: Vec3, field_name: str) -> None:
    if not isinstance(vec, tuple) or len(vec) != 3:
        raise ValueError(f"El campo '{field_name}' debe ser una tupla Vec3 de 3 elementos (recibido: {vec}).")
    for idx, component in enumerate(vec):
        validate_finite(component, f"{field_name}[{idx}]")


# --- Estructuras del dominio ---

@dataclass(frozen=True)
class CelestialBody:
    id: str
    name: str
    mu_m3_s2: float
    radius_m: float
    mass: float

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("El 'id' del cuerpo celeste no puede estar vacío.")
        if not self.name or not self.name.strip():
            raise ValueError("El 'name' del cuerpo celeste no puede estar vacío.")
        validate_positive(self.mu_m3_s2, "mu_m3_s2")
        validate_positive(self.radius_m, "radius_m")


@dataclass(frozen=True)
class SpacecraftState:
    position_m: Vec3
    velocity_m_s: Vec3

    def __post_init__(self) -> None:
        validate_vec3(self.position_m, "position_m")
        validate_vec3(self.velocity_m_s, "velocity_m_s")


@dataclass(frozen=True)
class SimulationConfig:
    scenario_id: str
    initial_state: SpacecraftState
    duration_s: float
    step_s: float

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.scenario_id.strip():
            raise ValueError("El 'scenario_id' no puede estar vacío.")
        if not isinstance(self.initial_state, SpacecraftState):
            raise TypeError("'initial_state' debe ser una instancia de SpacecraftState.")
        validate_positive(self.duration_s, "duration_s")
        validate_positive(self.step_s, "step_s")


@dataclass(frozen=True)
class TrajectorySample:
    t_s: float
    spacecraft: SpacecraftState
    body_positions_m: dict[str, Vec3]

    def __post_init__(self) -> None:
        validate_non_negative(self.t_s, "t_s")
        if not isinstance(self.spacecraft, SpacecraftState):
            raise TypeError("'spacecraft' debe ser una instancia de SpacecraftState.")
        if not self.body_positions_m:
            raise ValueError("'body_positions_m' debe incluir las posiciones de los cuerpos.")
        for body_id, pos in self.body_positions_m.items():
            if not body_id:
                raise ValueError("Las claves de 'body_positions_m' no pueden estar vacías.")
            validate_vec3(pos, f"body_positions_m['{body_id}']")


@dataclass(frozen=True)
class Event:
    type: EventType
    t_s: float
    body_id: str
    position_m: Vec3

    def __post_init__(self) -> None:
        if not isinstance(self.type, EventType):
            raise TypeError(f"'type' debe ser un EventType válido (recibido: {self.type}).")
        validate_non_negative(self.t_s, "t_s")
        if not self.body_id or not self.body_id.strip():
            raise ValueError("'body_id' no puede estar vacío.")
        validate_vec3(self.position_m, "position_m")


@dataclass(frozen=True)
class Diagnostics:
    final_time_s: float
    steps_completed: int
    min_distance_m: dict[str, float]
    min_altitude_m: dict[str, float]

    def __post_init__(self) -> None:
        validate_non_negative(self.final_time_s, "final_time_s")
        if isinstance(self.steps_completed, bool) or not isinstance(self.steps_completed, int) or self.steps_completed < 0:
            raise ValueError("'steps_completed' debe ser un entero mayor o igual que 0.")
        for body_id, dist in self.min_distance_m.items():
            validate_non_negative(dist, f"min_distance_m['{body_id}']")
        for body_id, alt in self.min_altitude_m.items():
            validate_finite(alt, f"min_altitude_m['{body_id}']")


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

    def __post_init__(self) -> None:
        if not isinstance(self.status, SimulationStatus):
            raise TypeError(f"'status' debe ser un SimulationStatus válido (recibido: {self.status}).")
        if not self.samples:
            raise ValueError("'samples' debe contener al menos la muestra inicial en t_s = 0.")
        if self.samples[0].t_s != 0.0:
            raise ValueError(f"La primera muestra debe tener t_s = 0.0 (recibido: {self.samples[0].t_s}).")
        for i in range(1, len(self.samples)):
            if self.samples[i].t_s <= self.samples[i - 1].t_s:
                raise ValueError("Los tiempos de las muestras deben ser estrictamente crecientes.")
        for i in range(1, len(self.events)):
            if self.events[i].t_s < self.events[i - 1].t_s:
                raise ValueError("Los eventos deben estar ordenados cronológicamente.")