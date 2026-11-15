/**
 * Catálogo visual: los iconos y tamaños facilitan la selección.
 * Las posiciones se obtienen exclusivamente desde la API de efemérides NASA.
 */
export type Planet = {
  id: string; name: string; asset: string; color: string
  radius: number; size: number
}

export const SOLAR_CENTER = { x: 700, y: 395 }
export const ORBIT_FLAT = .60
export const PLANETS: Planet[] = [
  { id: 'mercury', name: 'Mercurio', asset: 'mercurio.svg', color: '#b8b5b2', radius: 77, size: 17 },
  { id: 'venus', name: 'Venus', asset: 'venus.svg', color: '#f6c68d', radius: 115, size: 23 },
  { id: 'earth', name: 'Tierra', asset: 'tierra.svg', color: '#66c8ff', radius: 161, size: 29 },
  { id: 'mars', name: 'Marte', asset: 'marte.svg', color: '#ea9773', radius: 210, size: 24 },
  { id: 'jupiter', name: 'Júpiter', asset: 'jupiter.svg', color: '#e4b392', radius: 284, size: 48 },
  { id: 'saturn', name: 'Saturno', asset: 'saturno.svg', color: '#f4dfad', radius: 365, size: 68 },
  { id: 'uranus', name: 'Urano', asset: 'urano.svg', color: '#81efeb', radius: 448, size: 34 },
  { id: 'neptune', name: 'Neptuno', asset: 'neptuno.svg', color: '#6294ff', radius: 527, size: 34 },
]

export const BODIES = [
  { id: 'sun', name: 'Sol', asset: 'sol.svg', color: '#ffd166', radius: 0, size: 50 },
  ...PLANETS,
  { id: 'moon', name: 'Luna', asset: 'luna.svg', color: '#ddd', radius: 175, size: 17 },
]
export const bodyName = (id: string) => BODIES.find(b => b.id === id)?.name ?? id
export const bodyAsset = (id: string) => '/resource/' + (BODIES.find(b => b.id === id)?.asset ?? 'tierra.svg')
