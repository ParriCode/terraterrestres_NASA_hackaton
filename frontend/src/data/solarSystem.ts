import type { EphemerisSnapshot } from '../types/simulation'

export type PlanetId = 'sun' | 'mercury' | 'venus' | 'earth' | 'mars' | 'jupiter' | 'saturn' | 'uranus' | 'neptune'
export type Planet = {
  id: PlanetId; name: string; asset: string; color: string; radius: number; size: number;
  periodDays: number; phase: number; description: string
}

/** Radios son unidades de DISEÑO, no distancias reales */
export const PLANETS: Planet[] = [
  { id: 'mercury', name: 'Mercurio', asset: 'mercurio.svg', color: '#aeb1bd', radius: 74, size: 16, periodDays: 88, phase: 0.85, description: 'Planeta rocoso interior' },
  { id: 'venus', name: 'Venus', asset: 'venus.svg', color: '#e9bd80', radius: 112, size: 22, periodDays: 224.7, phase: 2.15, description: 'Planeta rocoso interior' },
  { id: 'earth', name: 'Tierra', asset: 'tierra.svg', color: '#53b5ff', radius: 157, size: 28, periodDays: 365.25, phase: -0.8, description: 'Origen de las misiones del MVP' },
  { id: 'mars', name: 'Marte', asset: 'marte.svg', color: '#e78a60', radius: 208, size: 22, periodDays: 687, phase: 3.2, description: 'Objetivo de una futura misión' },
  { id: 'jupiter', name: 'Júpiter', asset: 'jupiter.svg', color: '#e1a17b', radius: 278, size: 46, periodDays: 4332.6, phase: 0.6, description: 'Gigante gaseoso' },
  { id: 'saturn', name: 'Saturno', asset: 'saturno.svg', color: '#e9d5a5', radius: 363, size: 62, periodDays: 10759, phase: 3.65, description: 'Gigante gaseoso con anillos' },
  { id: 'uranus', name: 'Urano', asset: 'urano.svg', color: '#7ee7e3', radius: 446, size: 30, periodDays: 30688, phase: 2.1, description: 'Gigante helado' },
  { id: 'neptune', name: 'Neptuno', asset: 'neptuno.svg', color: '#5a8fff', radius: 528, size: 30, periodDays: 60182, phase: -0.3, description: 'Gigante helado' },
]

const ANCHOR = Date.UTC(2026, 10, 14, 0, 0, 0)
const AU_M = 149_597_870_700
export const SOLAR_CENTER = { x: 700, y: 394 }
export const ORBIT_FLAT = 0.60

export function planetaryPosition(planet: Planet, date: Date, ephemerides: EphemerisSnapshot | null): { x: number; y: number } {
  // Cuando existan datos del backend, se utiliza la dirección heliocéntrica real
  // El radio visual se comprime para que los ocho planetas quepan en el visor
  if (ephemerides?.positions_m[planet.id] && ephemerides.positions_m.sun) {
    const r = ephemerides.positions_m[planet.id]
    const sun = ephemerides.positions_m.sun
    const dx = r[0] - sun[0], dy = r[1] - sun[1]
    const au = Math.hypot(dx, dy) / AU_M
    const radius = Math.min(565, 151 * Math.log1p(au))
    const theta = Math.atan2(dy, dx)
    return { x: SOLAR_CENTER.x + Math.cos(theta) * radius, y: SOLAR_CENTER.y + Math.sin(theta) * radius * ORBIT_FLAT }
  }
  // SÓLO PRESENTACIÓN. Fases y períodos ficticios para ilustrar interactividad
  const days = (date.getTime() - ANCHOR) / 86_400_000
  const theta = planet.phase + days * 2 * Math.PI / planet.periodDays
  return { x: SOLAR_CENTER.x + Math.cos(theta) * planet.radius, y: SOLAR_CENTER.y + Math.sin(theta) * planet.radius * ORBIT_FLAT }
}

export function moonAngle(date: Date, ephemerides: EphemerisSnapshot | null): number {
  const earth = ephemerides?.positions_m.earth
  const moon = ephemerides?.positions_m.moon
  if (earth && moon) return Math.atan2(moon[1] - earth[1], moon[0] - earth[0])
  return -0.5 + ((date.getTime() - ANCHOR) / 86_400_000) * 2 * Math.PI / 27.321661
}
