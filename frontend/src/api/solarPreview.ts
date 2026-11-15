import { API_BASE_URL } from './transfers'
import { BODIES } from '../data/solarSystem'
import type { Vec3 } from '../types/transfer'

import type { SolarTable } from '../utils/solarInterpolation'
export type SolarSnapshot = { day: string; tables: Record<string, SolarTable>; loading: boolean; error?: string }
type Entry = { snapshot: SolarSnapshot; listeners: Set<(s: SolarSnapshot) => void> }
const days = new Map<string, Entry>()
const validVector = (v: unknown): v is Vec3 => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite)

export function cachedSolarDay(day: string) { return days.get(day)?.snapshot }

function validate(value: SolarTable, day: string) {
  return BODIES.some(b => b.id === value.body_id) && value.date?.slice(0, 10) === day
    && Array.isArray(value.times_s) && value.times_s.length === 25
    && value.times_s.every((t, i) => t === i * 3600)
    && Array.isArray(value.positions_m) && value.positions_m.length === 25 && value.positions_m.every(validVector)
    && Array.isArray(value.velocities_m_s) && value.velocities_m_s.length === 25 && value.velocities_m_s.every(validVector)
}

async function download(entry: Entry) {
  const notify = () => entry.listeners.forEach(listener => listener(entry.snapshot))
  try {
    const response = await fetch(`${API_BASE_URL}/ephemeris/solar-day?date=${entry.snapshot.day}T00:00:00Z`, { signal: AbortSignal.timeout(240000) })
    if (!response.ok || !response.body) throw new Error('No se pudo consultar NASA. Comprueba la conexión y reinicia el backend actualizado.')
    const reader = response.body.getReader(), decoder = new TextDecoder()
    let pending = ''
    const consume = (line: string) => {
      if (!line.trim()) return
      const row = JSON.parse(line)
      if (row.error) throw new Error(row.error)
      if (!validate(row, entry.snapshot.day)) throw new Error('NASA devolvió una tabla incompleta o inválida.')
      entry.snapshot = { ...entry.snapshot, tables: { ...entry.snapshot.tables, [row.body_id]: row } }
      notify()
    }
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        pending += decoder.decode(value, { stream: true })
        const lines = pending.split('\n'); pending = lines.pop() ?? ''
        lines.forEach(consume)
      }
      pending += decoder.decode()
      consume(pending)
      if (Object.keys(entry.snapshot.tables).length !== BODIES.length) throw new Error('La descarga NASA quedó incompleta.')
    } finally { await reader.cancel().catch(() => {}) }
    entry.snapshot = { ...entry.snapshot, loading: false }
  } catch (e) {
    entry.snapshot = { ...entry.snapshot, loading: false, error: e instanceof Error ? e.message : 'Error consultando NASA' }
    // A future subscription can retry; successful responses stay cached.
    days.delete(entry.snapshot.day)
  }
  notify()
}

/** One in-flight request per UTC day, shared across remounts and subscribers. */
export function subscribeSolarDay(day: string, listener: (s: SolarSnapshot) => void) {
  let entry = days.get(day)
  if (!entry) {
    for (const [key, value] of days) {
      if (days.size < 8) break
      if (!value.snapshot.loading && !value.listeners.size) days.delete(key)
    }
    entry = { snapshot: { day, tables: {}, loading: true }, listeners: new Set() }
    days.set(day, entry)
    void download(entry)
  }
  entry.listeners.add(listener)
  listener(entry.snapshot)
  const subscribed = entry
  return () => { subscribed.listeners.delete(listener) }
}

