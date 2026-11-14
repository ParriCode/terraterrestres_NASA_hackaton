/** Contrato de POST /transfers y POST /transfers/optimize. Todo en SI. */
export type Vec3 = [number, number, number]
export type TransferObjective = 'energia' | 'distancia' | 'delta_v'

export type TransferRequest = {
  date: string // ISO 8601 con zona horaria
  duration_s: number
  launch_angle_deg: number
  arrival_angle_deg: number
  objective: Exclude<TransferObjective, 'delta_v'>
  mass_kg: number
  samples: number
}

export type TransferSample = {
  t_s: number
  position_m: Vec3
  velocity_m_s: Vec3
  body_positions_m: { earth: Vec3; moon: Vec3 }
}

export type TransferBody = { name: string; radius_m: number }

export type TransferResponse = {
  source: string
  date: string
  frame: 'earth_moon_barycentric_initial_orbital_plane'
  basis_icrf: number[][]
  objective: TransferObjective
  mass_kg: number
  initial_velocity_m_s: Vec3
  launch_speed_m_s: number
  launch_energy_j: number
  path_length_m: number
  arrival_error_m: number
  duration_s: number
  bodies: { earth: TransferBody; moon: TransferBody }
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
  status: 'no_feasible_solution'
  source: string
  date: string
  max_duration_s: number
  min_search_duration_s: number
  parking_alt_m: number
  reasons: string[]
  tradeoff: TradeoffPoint[]
}

export type OptimizeTransferResponse =
  | OptimizeTransferOkResponse
  | OptimizeTransferNoFeasibleResponse

/** Estado interpolado de la nave y los cuerpos en un instante. */
export type TransferState = {
  t_s: number
  position_m: Vec3
  velocity_m_s: Vec3
  earth_m: Vec3
  moon_m: Vec3
}