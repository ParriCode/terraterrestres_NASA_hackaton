/**
 * Mapa panorámico EXCLUSIVAMENTE ILUSTRATIVO.
 * Los radios comprimidos, fases y periodos no son efemérides JPL.
 * Nunca se usan estos puntos para la transferencia científica Tierra–Luna.
 */
export type Planet = {
  id: string; name: string; asset: string; color: string
  radius: number; size: number; periodDays: number; phase: number
}

export const SOLAR_CENTER = { x: 700, y: 395 }
export const ORBIT_FLAT = .60
export const PLANETS: Planet[] = [
  { id: 'mercury', name: 'Mercurio', asset: 'mercurio.svg', color: '#b8b5b2', radius: 77, size: 17, periodDays: 88, phase: .85 },
  { id: 'venus', name: 'Venus', asset: 'venus.svg', color: '#f6c68d', radius: 115, size: 23, periodDays: 224.7, phase: 2.15 },
  { id: 'earth', name: 'Tierra', asset: 'tierra.svg', color: '#66c8ff', radius: 161, size: 29, periodDays: 365.25, phase: -.8 },
  { id: 'mars', name: 'Marte', asset: 'marte.svg', color: '#ea9773', radius: 210, size: 24, periodDays: 687, phase: 3.2 },
  { id: 'jupiter', name: 'Júpiter', asset: 'jupiter.svg', color: '#e4b392', radius: 284, size: 48, periodDays: 4332.6, phase: .6 },
  { id: 'saturn', name: 'Saturno', asset: 'saturno.svg', color: '#f4dfad', radius: 365, size: 68, periodDays: 10759, phase: 3.65 },
  { id: 'uranus', name: 'Urano', asset: 'urano.svg', color: '#81efeb', radius: 448, size: 34, periodDays: 30688, phase: 2.1 },
  { id: 'neptune', name: 'Neptuno', asset: 'neptuno.svg', color: '#6294ff', radius: 527, size: 34, periodDays: 60182, phase: -.3 },
]

const ANCHOR = Date.UTC(2026, 10, 14)
export function visualPlanetPosition(p: Planet, date: Date) {
  const days = (date.getTime() - ANCHOR) / 86400000
  const theta = p.phase + days * Math.PI * 2 / p.periodDays
  return { x: SOLAR_CENTER.x + Math.cos(theta) * p.radius, y: SOLAR_CENTER.y + Math.sin(theta) * p.radius * ORBIT_FLAT }
}
