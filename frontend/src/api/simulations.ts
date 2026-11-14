import type { EphemerisSnapshot, SimulationConfig, SimulationResult, Vec3 } from '../types/simulation'

/**
 * Configurar en frontend/.env.local (nunca subir a Git):
 * VITE_API_BASE_URL=http://localhost:8000
 * VITE_SIMULATION_PATH=/simulations
 * VITE_EPHEMERIDES_PATH=/api/ephemerides  (solo cuando P5/P2 lo implementen)
 */
const baseURL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const simulationPath = import.meta.env.VITE_SIMULATION_PATH || '/simulations'
const ephemeridesPath = import.meta.env.VITE_EPHEMERIDES_PATH || ''

export class ApiError extends Error {
  readonly status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function isVec3(value: unknown): value is Vec3 {
  return Array.isArray(value) && value.length === 3 && value.every(v => typeof v === 'number' && Number.isFinite(v))
}

/** Validación ligera de estructura para evitar animar respuestas incompatibles */
export function isSimulationResult(value: unknown): value is SimulationResult {
  if (!value || typeof value !== 'object') return false
  const r = value as Partial<SimulationResult>
  return r.schema_version === '1.0' && r.frame === 'earth_moon_barycentric_inertial'
    && !!r.config && typeof r.config.date === 'string'
    && Number.isFinite(Date.parse(r.config.date)) && !!r.diagnostics && Array.isArray(r.samples)
    && r.samples.length > 0 && Array.isArray(r.events) && Array.isArray(r.bodies)
    && r.samples.every(s => Number.isFinite(s.t_s)
      && isVec3(s.spacecraft?.position_m) && isVec3(s.spacecraft?.velocity_m_s)
      && s.body_positions_m && isVec3(s.body_positions_m.earth) && isVec3(s.body_positions_m.moon))
    && r.samples.every((s, i) => i === 0 || s.t_s > r.samples![i - 1].t_s)
    && r.samples[0].t_s === 0
    && ['completed', 'collision', 'numerical_error'].includes(r.status ?? '')
}

export async function runSimulation(config: SimulationConfig): Promise<SimulationResult> {
  let response: Response
  try {
    response = await fetch(`${baseURL}${simulationPath}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config), signal: AbortSignal.timeout(90_000),
    })
  } catch {
    throw new ApiError('No se ha podido conectar con FastAPI. Comprueba que esté iniciado y que la ruta coincida con la de Rafa.')
  }
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null)
    const details = data && typeof data === 'object' && 'detail' in data
      ? JSON.stringify((data as {detail: unknown}).detail) : response.statusText
    throw new ApiError(`FastAPI: ${details}`, response.status)
  }
  const data: unknown = await response.json().catch(() => null)
  if (!isSimulationResult(data)) throw new ApiError('FastAPI ha respondido con un formato distinto al contrato JSON v1.')
  return data
}

/** La ruta de efemérides es optativa: no se inventan posiciones reales si no existe*/
export async function fetchEphemerides(iso: string, signal?: AbortSignal): Promise<EphemerisSnapshot | null> {
  if (!ephemeridesPath) return null
  const url = `${baseURL}${ephemeridesPath}${ephemeridesPath.includes('?') ? '&' : '?'}at=${encodeURIComponent(iso)}`
  const response = await fetch(url, { signal })
  if (!response.ok) throw new ApiError(`Efemérides: HTTP ${response.status}`, response.status)
  const data: unknown = await response.json()
  if (!data || typeof data !== 'object') throw new ApiError('Formato de efemérides incorrecto')
  const e = data as Partial<EphemerisSnapshot>
  if (e.frame !== 'ssb_icrf' || !e.positions_m || !['sun','mercury','venus','earth','mars','jupiter','saturn','uranus','neptune','moon'].every(id => isVec3(e.positions_m?.[id]))) {
    throw new ApiError('Faltan cuerpos o el marco SSB/ICRF en las efemérides')
  }
  return e as EphemerisSnapshot
}