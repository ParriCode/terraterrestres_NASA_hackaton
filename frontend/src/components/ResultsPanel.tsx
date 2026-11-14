import { useState } from 'react'
import type { Journey } from '../types/simulation'
import { downloadJourney, formatDuration, formatKm } from '../utils/trajectory'
import Icon from './Icon'

type Props = { journey: Journey | null }
export default function ResultsPanel({ journey }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  if (!journey) return null
  const d = journey.result.diagnostics
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
      <p className="results-disclaimer">{journey.source === 'demo'
        ? 'Valores y trayectorias sintéticos. No representan un viaje posible ni están validados.'
        : '*Estimaciones sobre las muestras. «Completada» no significa «misión viable». Verificar precisión con P1/P3.'}</p>
      <div className="results-footer"><span>{journey.result.events.length} eventos</span>
        <button onClick={() => downloadJourney(journey)}><Icon name="download" size={15} />JSON</button></div>
    </div>}
  </div>
}
