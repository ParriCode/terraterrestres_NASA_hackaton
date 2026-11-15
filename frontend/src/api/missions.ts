/** Adaptador del motor de misiones 3D al contrato de visualización existente.
 * No integra la nave en React: todas las muestras proceden del backend.
 */
import type { TransferRequest, TransferResponse, TransferSample, Vec3 } from '../types/transfer'
import { API_BASE_URL, ApiError } from './transfers'

type RawRoundTrip = {
  status: 'ok'
  source: string
  date: string
  mode: 'free_return' | 'lunar_orbit'
  frame: 'earth_moon_barycentric_orbital_3d'
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
  earth_departure_speed_m_s: number
  earth_departure_kinetic_energy_j: number
  earth_entry_relative_speed_m_s: number
  earth_entry_inbound: boolean
  earth_entry_validated: boolean
  actual_lunar_revolutions: number
  bodies: { earth: { name: string; radius_m: number }; moon: { name: string; radius_m: number } }
  samples: TransferSample[]
}

const finite = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x)
const vec3 = (v: unknown): v is Vec3 => Array.isArray(v) && v.length === 3 && v.every(finite)

function validTrip(raw: unknown): raw is RawRoundTrip {
  if (typeof raw !== 'object' || raw === null) return false
  const r = raw as Partial<RawRoundTrip>
  const numeric = [r.total_duration_s, r.outbound_duration_s, r.lunar_stay_s, r.inbound_duration_s,
    r.total_delta_v_m_s, r.tli_delta_v_m_s, r.loi_delta_v_m_s, r.tei_delta_v_m_s,
    r.min_lunar_altitude_m, r.earth_reentry_altitude_m, r.earth_departure_speed_m_s,
    r.earth_departure_kinetic_energy_j, r.earth_entry_relative_speed_m_s, r.actual_lunar_revolutions]
  return r.status === 'ok' && r.earth_entry_validated === true && r.earth_entry_inbound === true
    && r.frame === 'earth_moon_barycentric_orbital_3d' && !!r.date && !!r.source
    && numeric.every(finite)
    && Array.isArray(r.basis_icrf) && r.basis_icrf.length === 3
    && r.basis_icrf.every(a => Array.isArray(a) && a.length === 3 && a.every(finite))
    && finite(r.bodies?.earth?.radius_m) && finite(r.bodies?.moon?.radius_m)
    && Array.isArray(r.samples) && r.samples.length >= 2 && r.samples[0].t_s === 0
    && r.samples.every((s, i) => finite(s.t_s) && (i === 0 || s.t_s > r.samples![i - 1].t_s)
      && vec3(s.position_m) && vec3(s.velocity_m_s)
      && vec3(s.body_positions_m?.earth) && vec3(s.body_positions_m?.moon))
    && finite(r.total_duration_s) && Math.abs(r.samples[r.samples.length - 1].t_s - r.total_duration_s) < 1
}

export async function requestRoundTripMission(
  form: TransferRequest, signal?: AbortSignal,
): Promise<TransferResponse> {
  const mode = form.mission_mode === 'free_return' ? 'free_return' : 'lunar_orbit'
  const url = `${API_BASE_URL}/missions/round-trip`
  const timeout = AbortSignal.timeout(10 * 60_000)
  const payload = {
    date: form.date,
    mode,
    mass_kg: form.mass_kg,
    max_total_duration_s: form.duration_s,
    lunar_periapsis_alt_m: (form.orbit_altitude_km ?? 150) * 1000,
    reentry_alt_m: 120000,
    samples: Math.min(4000, Math.max(500, form.samples, 200 + 18 * (form.lunar_revolutions ?? 1))),
    ...(mode === 'lunar_orbit' ? { lunar_revolutions: form.lunar_revolutions ?? 1 } : {}),
  }
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    if (timeout.aborted) throw new ApiError(0, 'El optimizador de misiones superó el límite de espera de 10 minutos.')
    throw new ApiError(0, `No se pudo conectar con ${url}. Comprueba que FastAPI está arrancado.`)
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const d = (data as { detail?: unknown } | null)?.detail
    const message = typeof d === 'string' ? d : JSON.stringify(d ?? response.statusText)
    throw new ApiError(response.status, `Motor orbital (HTTP ${response.status}): ${message}`)
  }
  if (data && typeof data === 'object' && (data as { status?: string }).status === 'no_feasible_solution') {
    const reasons = (data as { reasons?: string[] }).reasons ?? []
    throw new ApiError(422, `No se encontró una trayectoria validada en esta ventana: ${reasons.join(' · ') || 'sin candidato'}. Prueba otra fecha o duración.`)
  }
  if (!validTrip(data)) throw new ApiError(0, 'La respuesta 3D de la misión no confirma una trayectoria completa de regreso o no cumple el contrato.')

  const samples = data.samples
  const distance = samples.reduce((sum, sample, i) => {
    if (i === 0) return 0
    const prev = samples[i - 1].position_m
    return sum + Math.hypot(...sample.position_m.map((v, j) => v - prev[j]))
  }, 0)
  const tOut = data.outbound_duration_s
  const tTei = tOut + data.lunar_stay_s
  const maneuvers: NonNullable<TransferResponse['maneuvers']> = data.mode === 'lunar_orbit' ? [
    { phase: 'inserción_orbital', t_s: tOut, delta_v_m_s: data.loi_delta_v_m_s },
    { phase: 'inyección_retorno', t_s: tTei, delta_v_m_s: data.tei_delta_v_m_s },
  ] : []
  const bodyRadius = data.bodies.earth.radius_m
  const altitudeKm = (form.orbit_altitude_km ?? 150)
  return {
    mission_mode: data.mode === 'free_return' ? 'free_return' : 'lunar_orbit_return',
    source: data.source, date: data.date,
    frame: data.frame, basis_icrf: data.basis_icrf,
    objective: 'energia', mass_kg: form.mass_kg,
    initial_velocity_m_s: samples[0].velocity_m_s,
    launch_speed_m_s: data.earth_departure_speed_m_s,
    launch_energy_j: data.earth_departure_kinetic_energy_j,
    // Longitud aproximada como polilínea de muestras (no integral exacta).
    path_length_m: distance, path_length_approximate: true,
    arrival_angle_deg: null,
    arrival_error_m: Math.abs(data.earth_reentry_altitude_m - 120000),
    duration_s: data.total_duration_s,
    requested_duration_s: form.duration_s,
    bodies: data.bodies,
    samples,
    maneuvers,
    total_maneuver_delta_v_m_s: data.loi_delta_v_m_s + data.tei_delta_v_m_s,
    mission_solution: {
      mode: data.mode,
      total_delta_v_m_s: data.total_delta_v_m_s,
      tli_delta_v_m_s: data.tli_delta_v_m_s,
      loi_delta_v_m_s: data.loi_delta_v_m_s,
      tei_delta_v_m_s: data.tei_delta_v_m_s,
      min_lunar_altitude_km: data.min_lunar_altitude_m / 1000,
      actual_lunar_revolutions: data.actual_lunar_revolutions,
      outbound_duration_s: tOut,
      lunar_stay_s: data.lunar_stay_s,
      inbound_duration_s: data.inbound_duration_s,
    },
    earth_entry: {
      altitude_km: data.earth_reentry_altitude_m / 1000,
      relative_speed_m_s: data.earth_entry_relative_speed_m_s,
      inbound: data.earth_entry_inbound, validated: data.earth_entry_validated,
      landing_simulated: false,
    },
    return_interface_radius_m: bodyRadius + 120000,
    ...(data.mode === 'lunar_orbit' ? { lunar_orbit: {
      altitude_km: altitudeKm,
      revolutions: form.lunar_revolutions ?? 1,
      actual_revolutions: data.actual_lunar_revolutions,
      orbit_insertion_t_s: tOut,
      orbit_departure_t_s: tTei,
      orbital_period_s: data.lunar_stay_s / Math.max(1, form.lunar_revolutions ?? 1),
      return_arrival_direction_deg: null,
      verified_return: true,
    } } : {}),
    model_limitations: ['Propagación de misión con SciPy: solve_ivp/SciPy, no RK2.',
      'Llegada a 120 km de altitud; no se simulan atmósfera, reentrada ni aterrizaje.',
      'Búsqueda acotada; no garantiza el óptimo global.'],
  }
}

type RawOptimizedOneWay = {
  status: 'ok'; source: string; date: string
  frame: 'earth_moon_barycentric_initial_orbital_plane'
  basis_icrf: number[][]
  objective: 'delta_v'; mass_kg: number
  duration_s: number; max_duration_s: number
  launch_angle_deg: number; arrival_angle_deg: number
  initial_velocity_m_s: Vec3
  launch_speed_m_s: number; launch_energy_j: number
  path_length_m: number; arrival_error_m: number
  total_delta_v_m_s: number
  bodies: { earth: { name: string; radius_m: number }; moon: { name: string; radius_m: number } }
  samples: TransferSample[]
}

function validOutbound(x: unknown): x is RawOptimizedOneWay {
  if (!x || typeof x !== 'object') return false
  const r = x as Partial<RawOptimizedOneWay>
  return r.status === 'ok' && r.objective === 'delta_v'
    && r.frame === 'earth_moon_barycentric_initial_orbital_plane'
    && !!r.date && !!r.source
    && [r.duration_s, r.max_duration_s, r.arrival_angle_deg, r.total_delta_v_m_s,
      r.launch_speed_m_s, r.launch_energy_j, r.path_length_m, r.arrival_error_m].every(finite)
    && vec3(r.initial_velocity_m_s)
    && Array.isArray(r.basis_icrf) && r.basis_icrf.length === 2
    && r.basis_icrf.every(axis => axis.length === 3 && axis.every(finite))
    && finite(r.bodies?.earth?.radius_m) && finite(r.bodies?.moon?.radius_m)
    && Array.isArray(r.samples) && r.samples.length >= 2
    && r.samples.every((s, i) => finite(s.t_s) && (i === 0 || s.t_s > r.samples![i - 1].t_s)
      && vec3(s.position_m) && vec3(s.velocity_m_s)
      && vec3(s.body_positions_m.earth) && vec3(s.body_positions_m.moon))
}

export async function requestOptimizedOutbound(form: TransferRequest, signal?: AbortSignal): Promise<TransferResponse> {
  const url = `${API_BASE_URL}/missions/optimize`
  const timeout = AbortSignal.timeout(10 * 60_000)
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: form.date, max_duration_s: form.duration_s,
        mass_kg: form.mass_kg, samples: form.samples }),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    if (timeout.aborted) throw new ApiError(0, 'La transferencia orbital excedió el tiempo de espera.')
    throw new ApiError(0, `No fue posible conectar con ${url}.`)
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, `No se pudo ejecutar el optimizador de misiones: ${JSON.stringify((data as { detail?: unknown } | null)?.detail ?? data)}`)
  }
  if (data && typeof data === 'object' && (data as { status?: string }).status === 'no_feasible_solution') {
    throw new ApiError(422, `No se encontró una transferencia viable: ${((data as { reasons?: string[] }).reasons ?? []).join(' · ')}`)
  }
  if (!validOutbound(data)) throw new ApiError(0, 'Respuesta de optimización unidireccional de la misión incompatible.')
  return {
    source: data.source, date: data.date, frame: data.frame,
    basis_icrf: data.basis_icrf, objective: 'energia', mass_kg: form.mass_kg,
    initial_velocity_m_s: data.initial_velocity_m_s, launch_speed_m_s: data.launch_speed_m_s,
    launch_energy_j: data.launch_energy_j, path_length_m: data.path_length_m,
    arrival_error_m: data.arrival_error_m, arrival_angle_deg: data.arrival_angle_deg,
    duration_s: data.duration_s, requested_duration_s: form.duration_s,
    bodies: data.bodies, samples: data.samples,
    mission_one_way_delta_v_m_s: data.total_delta_v_m_s,
    model_limitations: ['ORBITAL4B optimiza Δv, no minimiza exactamente la energía ni la distancia.',
      'La duración es un máximo, no una fecha de llegada fija.', 'Búsqueda acotada sin garantía de óptimo global.'],
  }
}
