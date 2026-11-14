"""Contratos de respuesta para los tres endpoints /transfers (unidades SI)."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Vec3 = tuple[float, float, float]
Frame = Literal[
    "earth_moon_barycentric_initial_orbital_plane",
    "earth_moon_barycentric_orbital_3d",
]


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BodyResponse(_Response):
    name: str
    radius_m: float = Field(gt=0)


class SampleResponse(_Response):
    t_s: float = Field(ge=0)
    position_m: Vec3
    velocity_m_s: Vec3
    body_positions_m: dict[Literal["earth", "moon", "sun"], Vec3]


class PropellantResponse(_Response):
    initial_mass_kg: float = Field(gt=0)
    isp_s: float = Field(gt=0)
    propellant_mass_kg: float = Field(ge=0)
    final_mass_kg: float = Field(ge=0)
    mass_fraction: float = Field(ge=0, le=1)
    idealized: Literal[True]


class TradeoffResponse(_Response):
    duration_s: float = Field(gt=0)
    estimated_launch_delta_v_m_s: float = Field(ge=0)
    estimated_arrival_delta_v_m_s: float = Field(ge=0)
    estimated_total_delta_v_m_s: float = Field(ge=0)


class TransferResponse(_Response):
    source: str
    date: AwareDatetime
    frame: Frame
    basis_icrf: list[list[float]]
    objective: Literal["energia", "distancia", "delta_v"]
    mass_kg: float = Field(gt=0)
    initial_velocity_m_s: Vec3
    launch_speed_m_s: float = Field(ge=0)
    launch_energy_j: float = Field(ge=0)
    path_length_m: float = Field(ge=0)
    arrival_error_m: float = Field(ge=0)
    duration_s: float = Field(gt=0)
    bodies: dict[Literal["earth", "moon", "sun"], BodyResponse]
    samples: list[SampleResponse] = Field(min_length=2)


class OptimizedTransferOkResponse(TransferResponse):
    status: Literal["ok"]
    max_duration_s: float = Field(gt=0)
    min_search_duration_s: float = Field(gt=0)
    parking_alt_m: float = Field(ge=0)
    launch_angle_deg: float
    arrival_angle_deg: float
    launch_delta_v_m_s: float = Field(ge=0)
    arrival_v_infinity_m_s: float = Field(ge=0)
    arrival_delta_v_m_s: float = Field(ge=0)
    total_delta_v_m_s: float = Field(ge=0)
    propellant: PropellantResponse | None
    tradeoff: list[TradeoffResponse]


class NoFeasibleOneWayResponse(_Response):
    status: Literal["no_feasible_solution"]
    source: str
    date: AwareDatetime
    max_duration_s: float = Field(gt=0)
    min_search_duration_s: float = Field(gt=0)
    parking_alt_m: float = Field(ge=0)
    reasons: list[str]
    tradeoff: list[TradeoffResponse]


class RoundTripOkResponse(_Response):
    status: Literal["ok"]
    source: str
    mode: Literal["free_return", "lunar_orbit"]
    date: AwareDatetime
    frame: Frame
    basis_icrf: list[list[float]]
    outbound_duration_s: float = Field(gt=0)
    lunar_stay_s: float = Field(ge=0)
    inbound_duration_s: float = Field(gt=0)
    total_duration_s: float = Field(gt=0)
    tli_delta_v_m_s: float = Field(ge=0)
    loi_delta_v_m_s: float = Field(ge=0)
    tei_delta_v_m_s: float = Field(ge=0)
    total_delta_v_m_s: float = Field(ge=0)
    min_lunar_altitude_m: float
    earth_reentry_altitude_m: float
    propellant: PropellantResponse | None
    bodies: dict[Literal["earth", "moon", "sun"], BodyResponse]
    samples: list[SampleResponse] = Field(min_length=2)


class NoFeasibleRoundTripResponse(_Response):
    status: Literal["no_feasible_solution"]
    source: str
    mode: Literal["free_return", "lunar_orbit"]
    date: AwareDatetime
    max_total_duration_s: float = Field(gt=0)
    reasons: list[str]


OptimizedResponse = OptimizedTransferOkResponse | NoFeasibleOneWayResponse
RoundTripResponse = RoundTripOkResponse | NoFeasibleRoundTripResponse
