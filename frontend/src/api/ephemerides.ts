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

/** Dirección unitaria Tierra → Sol, obtenida de JPL Horizons. Nunca se sustituye por un mock. */
export type SunDirectionEphemeris = {
  source: 'NASA/JPL Horizons'
  date: string
  frame: 'earth_moon_barycentric_icrf'
  from: 'earth'
  toward: 'sun'
  direction_icrf: Vec3
}

export async function getSunDirection(date: Date, signal: AbortSignal): Promise<SunDirectionEphemeris> {
  const response = await fetch(`${API_BASE_URL}/ephemeris/sun-direction?date=${encodeURIComponent(date.toISOString())}`, { signal })
  if (!response.ok) throw new Error(`No se pudo consultar la dirección solar JPL (HTTP ${response.status}).`)
  const value: unknown = await response.json()
  if (!value || typeof value !== 'object') throw new Error('Respuesta solar vacía.')
  const data = value as Partial<SunDirectionEphemeris>
  if (data.source !== 'NASA/JPL Horizons' || data.frame !== 'earth_moon_barycentric_icrf'
    || data.from !== 'earth' || data.toward !== 'sun' || !validVec(data.direction_icrf)) {
    throw new Error('Dirección solar incompatible con el visor.')
  }
  const norm = Math.hypot(...data.direction_icrf)
  if (!(norm > 0.999 && norm < 1.001)) throw new Error('La dirección solar no está normalizada.')
  return data as SunDirectionEphemeris
}
