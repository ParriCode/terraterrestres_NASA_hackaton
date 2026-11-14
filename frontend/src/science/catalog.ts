/**
 * T11 · Catálogo PROVISIONAL DE INTERFAZ. Todos los números son hipótesis
 * educativas sintéticas, NO fichas NASA ni límites validados por P3.
 * Cuando Ángel facilite el catálogo real, sustituirlo de forma versionada
 */
export const SCIENCE_CATALOG_VERSION = 'ui-hypothesis-v1' as const

export const SCIENCE_GOALS = [
  { id: 'lunar_imaging', name: 'Cartografiar la Luna', description: 'Preparar observaciones visuales de la superficie durante el encuentro.', requiredInstrument: 'camera' },
  { id: 'lunar_composition', name: 'Estudiar la composición lunar', description: 'Planificar mediciones de composición mediante un espectrómetro.', requiredInstrument: 'spectrometer' },
  { id: 'space_radiation', name: 'Medir radiación en vuelo', description: 'Registrar niveles de radiación durante el recorrido.', requiredInstrument: 'dosimeter' },
] as const

export const SCIENCE_INSTRUMENTS = [
  { id: 'camera', name: 'Cámara científica', description: 'Captura imágenes de aproximación y sobrevuelo.', mass_kg: 12, power_w: 35, data_mb_day: 240 },
  { id: 'spectrometer', name: 'Espectrómetro', description: 'Registra mediciones espectrales de la superficie.', mass_kg: 18, power_w: 48, data_mb_day: 90 },
  { id: 'dosimeter', name: 'Dosímetro de radiación', description: 'Registra radiación del entorno de la nave.', mass_kg: 5, power_w: 12, data_mb_day: 12 },
  { id: 'thermal_camera', name: 'Cámara térmica', description: 'Registra observaciones térmicas complementarias.', mass_kg: 9, power_w: 28, data_mb_day: 150 },
] as const

export type ScienceGoalId = typeof SCIENCE_GOALS[number]['id']
export type ScienceInstrumentId = typeof SCIENCE_INSTRUMENTS[number]['id']
export type ScienceDesign = {
  goal_id: ScienceGoalId
  instrument_ids: ScienceInstrumentId[]
  catalog_version: typeof SCIENCE_CATALOG_VERSION
}

export type ScienceBudget = {
  mass_kg: number
  power_w: number
  data_mb_day: number
  projected_data_mb: number
  goal_has_required_instrument: boolean
}

export const DEFAULT_SCIENCE_DESIGN: ScienceDesign = {
  goal_id: 'lunar_imaging', instrument_ids: ['camera'], catalog_version: SCIENCE_CATALOG_VERSION,
}

export function scienceGoalName(id: ScienceGoalId): string {
  return SCIENCE_GOALS.find(goal => goal.id === id)?.name ?? 'Objetivo científico'
}

/** Proyección puramente aritmética: asume instrumentos activos las 24 h de cada día */
export function calculateScienceBudget(design: ScienceDesign, duration_s: number): ScienceBudget {
  const instruments = SCIENCE_INSTRUMENTS.filter(i => design.instrument_ids.includes(i.id))
  const mass_kg = instruments.reduce((sum, i) => sum + i.mass_kg, 0)
  const power_w = instruments.reduce((sum, i) => sum + i.power_w, 0)
  const data_mb_day = instruments.reduce((sum, i) => sum + i.data_mb_day, 0)
  const goal = SCIENCE_GOALS.find(g => g.id === design.goal_id)
  return {
    mass_kg, power_w, data_mb_day,
    projected_data_mb: data_mb_day * (Number.isFinite(duration_s) ? Math.max(0, duration_s) : 0) / 86400,
    goal_has_required_instrument: !!goal && design.instrument_ids.includes(goal.requiredInstrument),
  }
}
