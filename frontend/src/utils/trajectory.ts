import type { Journey, TrajectorySample, Vec3 } from '../types/simulation'

export const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n))
export const fmt = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })
export const formatKm = (meters: number) => `${fmt.format(meters / 1000)} km`

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.floor(seconds))
  const days = Math.floor(s / 86400)
  const hours = Math.floor((s % 86400) / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return days > 0 ? `${days} d ${String(hours).padStart(2, '0')} h ${String(minutes).padStart(2, '0')} min`
    : `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
export function elapsedAt(journey: Journey, date: Date): number {
  const raw = (date.getTime() - new Date(journey.launch_iso).getTime()) / 1000
  return clamp(raw, 0, journey.result.diagnostics.final_time_s)
}
export function journeyProgress(journey: Journey, date: Date) {
  const duration = journey.result.diagnostics.final_time_s
  return duration > 0 ? elapsedAt(journey, date) / duration : 0
}
function lerpVec(a: Vec3, b: Vec3, f: number): Vec3 {
  return [0, 1, 2].map(i => a[i] + (b[i] - a[i]) * f) as Vec3
}
/** Interpolación sólo GRÁFICA de muestras devueltas por Python */
export function sampleAt(samples: TrajectorySample[], t: number): TrajectorySample | null {
  if (!samples.length) return null
  if (t <= samples[0].t_s) return samples[0]
  const last = samples[samples.length - 1]
  if (t >= last.t_s) return last
  let left = 0, right = samples.length - 1
  while (left + 1 < right) {
    const mid = (left + right) >> 1
    if (samples[mid].t_s <= t) left = mid
    else right = mid
  }
  const a = samples[left], b = samples[right]
  const ratio = (t - a.t_s) / (b.t_s - a.t_s)
  const positions: Record<string, Vec3> = {}
  for (const key of Object.keys(a.body_positions_m)) {
    if (b.body_positions_m[key]) positions[key] = lerpVec(a.body_positions_m[key], b.body_positions_m[key], ratio)
  }
  return {
    t_s: t, body_positions_m: positions, spacecraft: {
      position_m: lerpVec(a.spacecraft.position_m, b.spacecraft.position_m, ratio),
      velocity_m_s: lerpVec(a.spacecraft.velocity_m_s, b.spacecraft.velocity_m_s, ratio),
    }
  }
}
export function projectRelativeToEarth(sample: TrajectorySample, metersToPixels: number, origin = { x: 700, y: 394 }) {
  const pos = sample.spacecraft.position_m
  const earth = sample.body_positions_m.earth
  return {
    x: origin.x + (pos[0] - earth[0]) * metersToPixels,
    y: origin.y - (pos[1] - earth[1]) * metersToPixels
  }
}
export function downloadJourney(journey: Journey) {
  const blob = new Blob([JSON.stringify({
    origin: journey.source, launch_iso: journey.launch_iso,
    route_kind: journey.route_kind ?? 'earth_moon', optimization_goal: journey.optimization_goal,
    min_flyby_altitude_km: journey.min_flyby_altitude_km, science: journey.science, result: journey.result
  }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a'); anchor.href = url
  anchor.download = `${journey.name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-') || 'viaje'}.json`
  document.body.appendChild(anchor); anchor.click(); anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
