import { useState } from 'react'
import type { Journey } from '../types/simulation'
import { downloadJourney, formatDuration, formatKm } from '../utils/trajectory'
import Icon from './Icon'
import { calculateScienceBudget, scienceGoalName } from '../science/catalog'

type Props = { journey: Journey | null }
export default function ResultsPanel({ journey }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  if (!journey) return null
  const d = journey.result.diagnostics
  const scienceBudget = journey.science ? calculateScienceBudget(journey.science, journey.result.config.duration_s) : null
  const collision = journey.result.status === 'collision'
  const numerical = journey.result.status === 'numerical_error'
  const status = journey.source === 'demo' ? 'Trayectoria de demostración'
    : collision ? 'Impacto registrado' : numerical ? 'Error numérico' : 'Propagación completada'
  return <div className={`results-panel ${collapsed ? 'collapsed' : ''}`}>
    <header className="results-heading"><div className="results-title"><Icon name="layers" size={17} /><span>DATOS DE LA MISIÓN</span></div>
      <button onClick={() => setCollapsed(s => !s)} className="results-collapse" title={collapsed ? 'Mostrar resultados' : 'Ocultar resultados'}>{collapsed ? 'Mostrar' : 'Ocultar'}</button></header>
    {!collapsed && <div className="results-body">
      <div className="result-status"><span className={journey.source === 'demo' ? 'status-demo' : collision || numerical ? 'status-warn' : 'status-okay'}><span className="small-dot" />{status}</span></div>
      <p className="mission-route-caption">{journey.route_kind === 'lunar_free_return' ? 'Tierra → sobrevuelo lunar → Tierra' : 'Tierra → Luna'} · {journey.optimization_goal === 'fuel' ? 'Prioridad: combustible' : journey.optimization_goal === 'time' ? 'Prioridad: duración' : journey.optimization_goal === 'safety' ? 'Prioridad: margen' : 'Sin prioridad de búsqueda'}</p>
      <div className="result-grid">
        <div><span>Tiempo final</span><strong>{formatDuration(d.final_time_s)}</strong></div>
        <div><span>Pasos completados</span><strong>{d.steps_completed.toLocaleString('es-ES')}</strong></div>
        <div><span>Altitud mín. Tierra*</span><strong>{Number.isFinite(d.min_altitude_m.earth) ? formatKm(d.min_altitude_m.earth) : '—'}</strong></div>
        <div><span>Altitud mín. Luna*</span><strong>{Number.isFinite(d.min_altitude_m.moon) ? formatKm(d.min_altitude_m.moon) : '—'}</strong></div>
      </div>
      {journey.science && scienceBudget && <details className="science-results-details">
        <summary><Icon name="target" size={14} /> Objetivo y carga científica</summary>
        <div className="science-results-body">
          <strong>{scienceGoalName(journey.science.goal_id)}</strong>
          <div className="science-result-metrics"><span>+{scienceBudget.mass_kg} kg de carga</span><span>+{scienceBudget.power_w} W requeridos</span><span>{scienceBudget.data_mb_day} MB/día (hipótesis)</span></div>
          <p>Volumen teórico si todos los instrumentos están activos durante toda la misión: <strong>{Math.round(scienceBudget.projected_data_mb).toLocaleString('es-ES')} MB</strong>.</p>
          <p className="science-results-unknown">No evaluado por P3: sin límites de potencia, masa, almacenamiento ni enlaces de comunicación. No se declara éxito científico.</p>
        </div>
      </details>}
      <p className="results-disclaimer">{journey.source === 'demo'
        ? 'Valores y trayectorias sintéticos. No representan un viaje posible ni están validados.'
        : '*Estimaciones sobre las muestras. «Completada» no significa «misión viable». Verificar precisión con P1/P3.'}</p>
      <div className="results-footer"><span>{journey.result.events.length} eventos</span>
        <button onClick={() => downloadJourney(journey)}><Icon name="download" size={15} />JSON</button></div>
    </div>}
  </div>
}
