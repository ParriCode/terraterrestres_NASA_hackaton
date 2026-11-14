import type { JourneyRouteKind, SimulationConfig, SimulationResult, TrajectorySample, Vec3 } from '../types/simulation'

const EARTH_R = 6_371_000, MOON_R = 1_737_400
const ORBIT_R = 384_400_000
const CENTER_EARTH: Vec3 = [-4_670_000, 0, 0]
const MOON_PERIOD = 27.321661 * 86_400
const earth = { id: 'earth', name: 'Tierra', mu_m3_s2: 3.986004418e14, radius_m: EARTH_R }
const moon = { id: 'moon', name: 'Luna', mu_m3_s2: 4.9048695e12, radius_m: MOON_R }
const vecDistance = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

/** Trayectoria SINTÉTICA sin ecuaciones orbitales: sólo prueba visual de UI */
function cubic(a: Vec3, b: Vec3, c: Vec3, d: Vec3, t: number): Vec3 {
  const q = 1 - t
  return [0, 1, 2].map(i => q * q * q * a[i] + 3 * q * q * t * b[i] + 3 * q * t * t * c[i] + t * t * t * d[i]) as Vec3
}
function add(origin: Vec3, radial: Vec3, tangent: Vec3, r: number, n: number): Vec3 {
  return [0, 1, 2].map(i => origin[i] + radial[i] * r + tangent[i] * n) as Vec3
}
/**
 * Dibujo sintético de ida, paso alrededor de la Luna y vuelta a la Tierra
 * NO calcula ni garantiza una órbita de retorno libre ni optimiza parámetros
 */
export function createDemoSimulation(config: SimulationConfig, variant: number,
  routeKind: JourneyRouteKind = 'earth_moon', minAltitudeKm = 1000): SimulationResult {
  const samples: TrajectorySample[] = []
  const count = 320
  const phase = 0.12 * variant
  const d = config.duration_s
  let minEarth = Infinity, minMoon = Infinity
  const midAngle = phase + (d / 2) / MOON_PERIOD * 2 * Math.PI
  const radial: Vec3 = [Math.cos(midAngle), Math.sin(midAngle), 0]
  const tangent: Vec3 = [-radial[1], radial[0], 0]
  const moonMid = add(CENTER_EARTH, radial, tangent, ORBIT_R, 0)
  const start = add(CENTER_EARTH, radial, tangent, EARTH_R + 350_000, 0)
  const flyby = add(moonMid, radial, tangent, 0, MOON_R + minAltitudeKm * 1000)
  const finish = add(CENTER_EARTH, radial, tangent, EARTH_R + 900_000, 0)
  const departC1 = add(CENTER_EARTH, radial, tangent, ORBIT_R * .29, ORBIT_R * .14)
  const departC2 = add(moonMid, radial, tangent, -ORBIT_R * .16, ORBIT_R * .2)
  const returnC1 = add(moonMid, radial, tangent, ORBIT_R * .19, ORBIT_R * .20)
  const returnC2 = add(CENTER_EARTH, radial, tangent, ORBIT_R * .19, -ORBIT_R * .12)
  for (let i = 0; i <= count; i++) {
    const p = i / count
    const t_s = p * d
    const theta = phase + t_s / MOON_PERIOD * 2 * Math.PI
    const moonPos: Vec3 = [CENTER_EARTH[0] + ORBIT_R * Math.cos(theta), ORBIT_R * Math.sin(theta), 0]
    const eased = p * p * (3 - 2 * p)
    const originDist = EARTH_R + 350_000
    const dx = moonPos[0] - CENTER_EARTH[0], dy = moonPos[1]
    const shipPos: Vec3 = routeKind === 'lunar_free_return'
      ? p <= .5 ? cubic(start, departC1, departC2, flyby, p * 2)
        : cubic(flyby, returnC1, returnC2, finish, (p - .5) * 2)
      : [
        CENTER_EARTH[0] + (1 - eased) * originDist + eased * dx,
        eased * dy + Math.sin(Math.PI * p) * (variant % 2 ? 1 : -1) * 22_000_000,
        0,
      ]
    const velocity: Vec3 = [0, 0, 0]  // Sólo visual; NO mide velocidad real
    minEarth = Math.min(minEarth, vecDistance(shipPos, CENTER_EARTH))
    minMoon = Math.min(minMoon, vecDistance(shipPos, moonPos))
    samples.push({
      t_s, spacecraft: { position_m: shipPos, velocity_m_s: velocity },
      body_positions_m: { earth: CENTER_EARTH, moon: moonPos }
    })
  }
  return {
    schema_version: '1.0', config, frame: 'earth_moon_barycentric_inertial',
    units: { length: 'm', time: 's', velocity: 'm/s', gravitational_parameter: 'm^3/s^2' },
    bodies: [earth, moon], status: 'completed', samples, events: [],
    diagnostics: {
      final_time_s: d, steps_completed: count,
      min_distance_m: { earth: minEarth, moon: minMoon },
      min_altitude_m: { earth: minEarth - EARTH_R, moon: minMoon - MOON_R }
    }
  }
}
