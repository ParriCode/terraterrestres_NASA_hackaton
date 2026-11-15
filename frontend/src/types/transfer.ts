/** Contrato de POST /transfers, POST /transfers/optimize y POST /transfers/round-trip. Todo en SI. */
export type Vec3 = [number, number, number]
export type TransferObjective = 'energia' | 'distancia'
export type MissionMode = 'lunar_transfer' | 'free_return' | 'lunar_orbit_return'

export type TransferRequest = {
  date: string // ISO 8601 con zona horaria
  mission_mode?: MissionMode
  orbit_altitude_km?: number
  lunar_stay_s?: number // tiempo fijo de estancia lunar, en segundos
  duration_s: number
  launch_angle_deg: number
  objective: TransferObjective
  mass_kg: number
  samples: number
}

export type TransferSample = {
  t_s: number
  position_m: Vec3
  velocity_m_s: Vec3
  body_positions_m: { earth: Vec3; moon: Vec3; sun?: Vec3 }
}

export type TransferBody = { name: string; radius_m: number }

export type TransferOptimization = {
  method: 'bounded_angle_search'
  attempted_angles_deg: number[]
  valid_candidates: number
  search_complete: boolean
  timed_out_angles_deg: number[]
  global_optimum_guaranteed: false
}

export type LunarManeuver = {
  phase: 'inserción_orbital' | 'inyección_retorno'
  t_s: number
  delta_v_m_s: number
  before_m_s?: Vec3
  after_m_s?: Vec3
}

export type LunarOrbitReport = {
  altitude_km: number
  actual_revolutions: number
  orbit_insertion_t_s: number
  orbit_departure_t_s: number
  return_arrival_direction_deg: number | null
  return_arrival_t_s?: number
  verified_return: boolean
}

export type TransferResponse = {
  mission_mode?: 'free_return' | 'lunar_orbit_return'
  return_interface_radius_m?: number
  earth_entry?: {
    altitude_km: number
    relative_speed_m_s: number
    inbound: boolean
    validated: boolean
    landing_simulated: false
  }
  requested_duration_s?: number // duración máxima, puede regresar antes
  lunar_orbit?: LunarOrbitReport
  maneuvers?: LunarManeuver[]
  total_maneuver_delta_v_m_s?: number
  model_limitations?: string[]
  path_length_approximate?: boolean
  mission_one_way_delta_v_m_s?: number
  mission_solution?: {
    mode: 'free_return' | 'lunar_orbit'
    total_delta_v_m_s: number
    tli_delta_v_m_s: number
    loi_delta_v_m_s: number
    tei_delta_v_m_s: number
    min_lunar_altitude_km: number
    actual_lunar_revolutions: number
    outbound_duration_s: number
    lunar_stay_s: number
    inbound_duration_s: number
  }
  source: string
  date: string
  frame: 'earth_moon_barycentric_initial_orbital_plane' | 'earth_moon_barycentric_orbital_3d'
  basis_icrf: number[][]
  objective: TransferObjective
  mass_kg: number
  initial_velocity_m_s: Vec3
  launch_speed_m_s: number
  launch_energy_j: number
  arrival_angle_deg: number | null // ángulo que eligió el optimizador de /transfers/optimize
  optimization?: TransferOptimization
  path_length_m: number
  arrival_error_m: number
  duration_s: number
  bodies: { earth: TransferBody; moon: TransferBody; sun?: TransferBody }
  samples: TransferSample[]
}

export type OptimizeTransferRequest = {
  date: string
  max_duration_s: number
  parking_alt_m: number
  samples: number
  initial_mass_kg?: number
  isp_s?: number
}

export type RoundTripRequest = {
  date: string
  mode: RoundTripMode
  max_total_duration_s: number
  parking_alt_m: number
  lunar_periapsis_alt_m: number
  lunar_stay_s: number
  reentry_alt_m: number
  samples: number
  initial_mass_kg?: number
  isp_s?: number
}

export type TradeoffPoint = {
  duration_s: number
  estimated_launch_delta_v_m_s: number
  estimated_arrival_delta_v_m_s: number
  estimated_total_delta_v_m_s: number
}

export type PropellantEstimate = {
  initial_mass_kg: number
  isp_s: number
  propellant_mass_kg: number
  final_mass_kg: number
  mass_fraction: number
  idealized: boolean
}

export type OptimizeTransferOkResponse = TransferResponse & {
  kind: 'one_way'
  status: 'ok'
  max_duration_s: number
  min_search_duration_s: number
  parking_alt_m: number
  launch_angle_deg: number
  arrival_angle_deg: number
  launch_delta_v_m_s: number
  arrival_v_infinity_m_s: number
  arrival_delta_v_m_s: number
  total_delta_v_m_s: number
  propellant: PropellantEstimate | null
  tradeoff: TradeoffPoint[]
}

export type OptimizeTransferNoFeasibleResponse = {
  kind: 'one_way'
  status: 'no_feasible_solution'
  source: string
  date: string
  max_duration_s: number
  min_search_duration_s: number
  parking_alt_m: number
  reasons: string[]
  tradeoff: TradeoffPoint[]
}

export type RoundTripOkResponse = {
  kind: 'round_trip'
  status: 'ok'
  source: string
  mode: RoundTripMode
  date: string
  frame: TransferFrame
  basis_icrf: number[][]
  outbound_duration_s: number
  lunar_stay_s: number
  inbound_duration_s: number
  total_duration_s: number
  tli_delta_v_m_s: number
  loi_delta_v_m_s: number
  tei_delta_v_m_s: number
  total_delta_v_m_s: number
  min_lunar_altitude_m: number
  earth_reentry_altitude_m: number
  propellant: PropellantEstimate | null
  bodies: { earth: TransferBody; moon: TransferBody; sun?: TransferBody }
  samples: TransferSample[]
}

export type RoundTripNoFeasibleResponse = {
  kind: 'round_trip'
  status: 'no_feasible_solution'
  source: string
  mode: RoundTripMode
  date: string
  max_total_duration_s: number
  reasons: string[]
}

export type OptimizeTransferResponse =
  | OptimizeTransferOkResponse
  | OptimizeTransferNoFeasibleResponse

export type RoundTripResponse =
  | RoundTripOkResponse
  | RoundTripNoFeasibleResponse

export type MissionSubmitPayload =
  | { kind: 'one_way'; payload: OptimizeTransferRequest }
  | { kind: 'round_trip'; payload: RoundTripRequest }

export type MissionResponse = OptimizeTransferResponse | RoundTripResponse
export type MissionOkResponse = OptimizeTransferOkResponse | RoundTripOkResponse

/** Estado interpolado de la nave y los cuerpos en un instante. */
export type TransferState = {
  t_s: number
  position_m: Vec3
  velocity_m_s: Vec3
  earth_m: Vec3
  moon_m: Vec3
}