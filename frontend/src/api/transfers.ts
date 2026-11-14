import type { TransferRequest, TransferResponse, Vec3 } from '../types/transfer'

/** Configurable en frontend/.env.local: VITE_API_BASE_URL=http://localhost:8000 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const TIMEOUT_MS = 5 * 60_000 // el cálculo es síncrono y puede probar varias semillas

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type ValidationItem = { loc?: unknown[]; msg?: string }

/** FastAPI devuelve detail como texto (HTTPException) u objeto (validación). */
function describeDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; suggestion?: string; errors?: ValidationItem[] }
    const items = Array.isArray(d.errors)
      ? d.errors.map(e => `${(e.loc ?? []).filter(l => l !== 'body').join('.')}: ${e.msg ?? ''}`)
      : []
    return [d.message, d.suggestion, ...items].filter(Boolean).join(' · ') || JSON.stringify(detail)
  }
  if (Array.isArray(detail)) return detail.map(e => (e as ValidationItem).msg).join(' · ')
  return ''
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isVec3 = (v: unknown): v is Vec3 => Array.isArray(v) && v.length === 3 && v.every(isNum)

function isTransferResponse(value: unknown): value is TransferResponse {
  if (!value || typeof value !== 'object') return false
  const r = value as Partial<TransferResponse>
  const s = r.samples
  return r.frame === 'earth_moon_barycentric_initial_orbital_plane'
    && typeof r.date === 'string' && Number.isFinite(Date.parse(r.date))
    && isVec3(r.initial_velocity_m_s) && isNum(r.launch_speed_m_s) && isNum(r.launch_energy_j)
    && isNum(r.path_length_m) && isNum(r.arrival_error_m) && isNum(r.duration_s) && isNum(r.arrival_angle_deg)
    && isNum(r.bodies?.earth?.radius_m) && isNum(r.bodies?.moon?.radius_m)
    && (r.optimization === undefined || (r.optimization.method === 'bounded_angle_search'
      && Array.isArray(r.optimization.attempted_angles_deg)
      && r.optimization.attempted_angles_deg.every(isNum)
      && isNum(r.optimization.valid_candidates)
      && Array.isArray(r.optimization.timed_out_angles_deg)
      && r.optimization.timed_out_angles_deg.every(isNum)
      && typeof r.optimization.search_complete === 'boolean'
      && r.optimization.global_optimum_guaranteed === false))
    && Array.isArray(s) && s.length >= 2 && s[0].t_s === 0
    && s.every((p, i) => isNum(p.t_s) && (i === 0 || p.t_s > s[i - 1].t_s)
      && isVec3(p.position_m) && isVec3(p.velocity_m_s)
      && isVec3(p.body_positions_m?.earth) && isVec3(p.body_positions_m?.moon))
}

export async function requestTransfer(body: TransferRequest, signal?: AbortSignal): Promise<TransferResponse> {
  const url = `${API_BASE_URL}/transfers/optimize`
  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    if (timeout.aborted) throw new ApiError(0, `El cálculo superó ${TIMEOUT_MS / 60_000} min sin respuesta.`)
    throw new ApiError(0, `No se pudo conectar con ${url}. Comprueba que el backend está arrancado y que CORS (ORBITAL_CORS_ORIGINS) admite ${window.location.origin}.`)
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = describeDetail((data as { detail?: unknown } | null)?.detail) || response.statusText
    if (response.status === 404 || response.status === 405) throw new ApiError(response.status, "POST /transfers/optimize no está disponible. Comprueba que has aplicado la actualización del backend y reiniciado FastAPI.")
    if (response.status === 422) {
      const code = (data as { detail?: { code?: string } } | null)?.detail?.code
      if (code === 'no_valid_transfer') {
        throw new ApiError(422, `No se encontró una transferencia válida: ${detail}`)
      }
      throw new ApiError(422, `Revisa los parámetros de la simulación: ${detail}`)
    }
    if (response.status === 502) throw new ApiError(502, `Fallo al consultar las efemérides de NASA/JPL Horizons: ${detail}`)
    throw new ApiError(response.status, `Error del backend (HTTP ${response.status}): ${detail}`)
  }
  if (!isTransferResponse(data)) throw new ApiError(0, 'El backend respondió con un formato distinto al esperado para /transfers/optimize (debe incluir arrival_angle_deg elegido por el optimizador).')
  return data
}
