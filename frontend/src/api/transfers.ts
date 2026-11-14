import type {
  OptimizeTransferNoFeasibleResponse,
  OptimizeTransferOkResponse,
  OptimizeTransferRequest,
  OptimizeTransferResponse,
  RoundTripNoFeasibleResponse,
  RoundTripOkResponse,
  RoundTripRequest,
  RoundTripResponse,
  TradeoffPoint,
  TransferRequest,
  TransferResponse,
  TransferSample,
  Vec3,
} from '../types/transfer'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const TIMEOUT_MS = 5 * 60_000

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type ValidationItem = { loc?: unknown[]; msg?: string }

function describeDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(e => (e as ValidationItem).msg).join(' · ')
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; errors?: ValidationItem[] }
    const items = Array.isArray(d.errors)
      ? d.errors.map(e => `${(e.loc ?? []).filter(l => l !== 'body').join('.')}: ${e.msg ?? ''}`)
      : []
    return [d.message, ...items].filter(Boolean).join(' · ') || JSON.stringify(detail)
  }
  return ''
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isVec3 = (v: unknown): v is Vec3 => Array.isArray(v) && v.length === 3 && v.every(isNum)

function isValidFrame(frame: unknown): boolean {
  return (
    frame === 'earth_moon_barycentric_initial_orbital_plane' ||
    frame === 'earth_moon_barycentric_orbital_3d'
  )
}

function isValidSamples(s: unknown): s is TransferSample[] {
  return (
    Array.isArray(s) &&
    s.length >= 2 &&
    s[0] != null &&
    s[0].t_s === 0 &&
    s.every(
      (p, i) =>
        p != null &&
        isNum(p.t_s) &&
        (i === 0 || p.t_s > s[i - 1].t_s) &&
        isVec3(p.position_m) &&
        isVec3(p.velocity_m_s) &&
        isVec3(p.body_positions_m?.earth) &&
        isVec3(p.body_positions_m?.moon) &&
        (p.body_positions_m?.sun === undefined || isVec3(p.body_positions_m.sun)),
    )
  )
}

function isTradeoffList(value: unknown): value is TradeoffPoint[] {
  return (
    Array.isArray(value) &&
    value.every(p => {
      if (!p || typeof p !== 'object') return false
      const pt = p as Partial<TradeoffPoint>
      return (
        isNum(pt.duration_s) &&
        isNum(pt.estimated_launch_delta_v_m_s) &&
        isNum(pt.estimated_arrival_delta_v_m_s) &&
        isNum(pt.estimated_total_delta_v_m_s)
      )
    })
  )
}

function isTransferResponse(value: unknown): value is TransferResponse {
  if (!value || typeof value !== 'object') return false
  const r = value as Partial<TransferResponse>
  return (
    isValidFrame(r.frame) &&
    typeof r.date === 'string' &&
    Number.isFinite(Date.parse(r.date)) &&
    isVec3(r.initial_velocity_m_s) &&
    isNum(r.launch_speed_m_s) &&
    isNum(r.launch_energy_j) &&
    isNum(r.path_length_m) &&
    isNum(r.arrival_error_m) &&
    isNum(r.duration_s) &&
    isNum(r.bodies?.earth?.radius_m) &&
    isNum(r.bodies?.moon?.radius_m) &&
    isValidSamples(r.samples)
  )
}

function isOptimizeOkResponse(value: unknown): value is Omit<OptimizeTransferOkResponse, 'kind'> {
  if (!isTransferResponse(value)) return false
  const r = value as Partial<OptimizeTransferOkResponse>
  return (
    r.status === 'ok' &&
    isNum(r.max_duration_s) &&
    isNum(r.min_search_duration_s) &&
    isNum(r.parking_alt_m) &&
    isNum(r.launch_delta_v_m_s) &&
    isNum(r.arrival_v_infinity_m_s) &&
    isNum(r.arrival_delta_v_m_s) &&
    isNum(r.total_delta_v_m_s) &&
    isTradeoffList(r.tradeoff)
  )
}

function isOptimizeNoFeasibleResponse(
  value: unknown,
): value is Omit<OptimizeTransferNoFeasibleResponse, 'kind'> {
  if (!value || typeof value !== 'object') return false
  const r = value as Partial<OptimizeTransferNoFeasibleResponse>
  return (
    r.status === 'no_feasible_solution' &&
    typeof r.date === 'string' &&
    Number.isFinite(Date.parse(r.date)) &&
    isNum(r.max_duration_s) &&
    isNum(r.min_search_duration_s) &&
    isNum(r.parking_alt_m) &&
    Array.isArray(r.reasons) &&
    r.reasons.every(item => typeof item === 'string') &&
    isTradeoffList(r.tradeoff)
  )
}

function isRoundTripOkResponse(value: unknown): value is Omit<RoundTripOkResponse, 'kind'> {
  if (!value || typeof value !== 'object') return false
  const r = value as Partial<RoundTripOkResponse>
  return (
    r.status === 'ok' &&
    (r.mode === 'free_return' || r.mode === 'lunar_orbit') &&
    isValidFrame(r.frame) &&
    typeof r.date === 'string' &&
    Number.isFinite(Date.parse(r.date)) &&
    isNum(r.outbound_duration_s) &&
    isNum(r.lunar_stay_s) &&
    isNum(r.inbound_duration_s) &&
    isNum(r.total_duration_s) &&
    isNum(r.tli_delta_v_m_s) &&
    isNum(r.loi_delta_v_m_s) &&
    isNum(r.tei_delta_v_m_s) &&
    isNum(r.total_delta_v_m_s) &&
    isNum(r.min_lunar_altitude_m) &&
    isNum(r.earth_reentry_altitude_m) &&
    isNum(r.bodies?.earth?.radius_m) &&
    isNum(r.bodies?.moon?.radius_m) &&
    isValidSamples(r.samples)
  )
}

function isRoundTripNoFeasibleResponse(
  value: unknown,
): value is Omit<RoundTripNoFeasibleResponse, 'kind'> {
  if (!value || typeof value !== 'object') return false
  const r = value as Partial<RoundTripNoFeasibleResponse>
  return (
    r.status === 'no_feasible_solution' &&
    (r.mode === 'free_return' || r.mode === 'lunar_orbit') &&
    typeof r.date === 'string' &&
    Number.isFinite(Date.parse(r.date)) &&
    isNum(r.max_total_duration_s) &&
    Array.isArray(r.reasons) &&
    r.reasons.every(item => typeof item === 'string')
  )
}

async function postJson(path: string, body: unknown, signal?: AbortSignal): Promise<unknown> {
  const url = `${API_BASE_URL}${path}`
  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    if (timeout.aborted) throw new ApiError(0, `El cálculo superó ${TIMEOUT_MS / 60_000} min sin respuesta.`)
    throw new ApiError(
      0,
      `No se pudo conectar con ${url}. Comprueba que el backend está arrancado y que CORS (ORBITAL_CORS_ORIGINS) admite ${window.location.origin}.`,
    )
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = describeDetail((data as { detail?: unknown } | null)?.detail) || response.statusText
    if (response.status === 422) throw new ApiError(422, `No se pudo calcular la transferencia: ${detail}`)
    if (response.status === 502) throw new ApiError(502, `Fallo al consultar las efemérides de NASA/JPL Horizons: ${detail}`)
    throw new ApiError(response.status, `Error del backend (HTTP ${response.status}): ${detail}`)
  }
  return data
}

export async function requestTransfer(body: TransferRequest, signal?: AbortSignal): Promise<TransferResponse> {
  const data = await postJson('/transfers', body, signal)
  if (!isTransferResponse(data)) {
    throw new ApiError(0, 'El backend respondió con un formato distinto al esperado para /transfers.')
  }
  return data
}

export async function requestOptimizedTransfer(
  body: OptimizeTransferRequest,
  signal?: AbortSignal,
): Promise<OptimizeTransferResponse> {
  const data = await postJson('/transfers/optimize', body, signal)
  if (isOptimizeOkResponse(data)) return { ...data, kind: 'one_way' }
  if (isOptimizeNoFeasibleResponse(data)) return { ...data, kind: 'one_way' }
  throw new ApiError(0, 'El backend respondió con un formato distinto al esperado para /transfers/optimize.')
}

export async function requestRoundTripTransfer(
  body: RoundTripRequest,
  signal?: AbortSignal,
): Promise<RoundTripResponse> {
  const data = await postJson('/transfers/round-trip', body, signal)
  if (isRoundTripOkResponse(data)) return { ...data, kind: 'round_trip' }
  if (isRoundTripNoFeasibleResponse(data)) {
    return { ...data, kind: 'round_trip' }
  }
  throw new ApiError(0, 'El backend respondió con un formato distinto al esperado para /transfers/round-trip.')
}