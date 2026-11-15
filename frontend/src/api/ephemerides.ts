import { API_BASE_URL } from './transfers'
import type { Vec3 } from '../types/transfer'

export type EarthMoonEphemeris = {
  source: 'NASA/JPL Horizons'
  date: string
  frame: 'earth_moon_barycentric_icrf'
  center: '500@3'
  units: 'm'
  body_positions_m: { earth: Vec3; moon: Vec3 }
}

const validVec = (v: unknown): v is Vec3 => Array.isArray(v) && v.length === 3
  && v.every(x => typeof x === 'number' && Number.isFinite(x))

/** Vista previa sin posiciones ficticias. Responde con datos JPL o con error. */
export async function getEarthMoonEphemeris(date: Date, signal: AbortSignal): Promise<EarthMoonEphemeris> {
  const response = await fetch(`${API_BASE_URL}/ephemeris/earth-moon?date=${encodeURIComponent(date.toISOString())}`, { signal })
  if (!response.ok) throw new Error(`No se pudieron obtener las efemérides JPL (HTTP ${response.status}).`)
  const data: unknown = await response.json()
  if (!data || typeof data !== 'object') throw new Error('Respuesta vacía de efemérides.')
  const value = data as Partial<EarthMoonEphemeris>
  if (value.source !== 'NASA/JPL Horizons' || value.frame !== 'earth_moon_barycentric_icrf'
    || value.units !== 'm' || !validVec(value.body_positions_m?.earth)
    || !validVec(value.body_positions_m?.moon)) {
    throw new Error('Respuesta de efemérides incompatible con el visor.')
  }
  return value as EarthMoonEphemeris
}
