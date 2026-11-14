import { useState } from 'react'
import type { JourneyRouteKind, OptimizationGoal, SimulationConfig } from '../types/simulation'
import Icon from './Icon'
import SciencePayloadSelector from './SciencePayloadSelector'
import { DEFAULT_SCIENCE_DESIGN, calculateScienceBudget } from '../science/catalog'
import type { ScienceDesign } from '../science/catalog'

export type NewJourneyForm = {
  name: string; launch_iso: string; config: SimulationConfig;
  route_kind: JourneyRouteKind; optimization_goal: OptimizationGoal; min_flyby_altitude_km: number; science: ScienceDesign
}
type Props = { open: boolean; busy: boolean; onClose: () => void; onDemo: (data: NewJourneyForm) => void; onBackend: (data: NewJourneyForm) => void }
function toLocal(date: Date) { const pad = (v: number) => String(v).padStart(2, '0'); return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}` }

export default function SimulationForm({ open, busy, onClose, onDemo, onBackend }: Props) {
  const [name, setName] = useState('Misión Artemis')
  const [routeKind, setRouteKind] = useState<JourneyRouteKind>('earth_moon')
  const [optimizationGoal, setOptimizationGoal] = useState<OptimizationGoal>('fuel')
  const [minAltitudeKm, setMinAltitudeKm] = useState(1000)
  const [start, setStart] = useState(() => toLocal(new Date(Date.now() - 12 * 3600_000)))
  const [durationH, setDurationH] = useState(72)
  const [step, setStep] = useState(900)
  const [position, setPosition] = useState<[number, number, number]>([2_001_000, 0, 0])
  const [velocity, setVelocity] = useState<[number, number, number]>([0, 10_800, 0])
  const [science, setScience] = useState<ScienceDesign>(() => ({ ...DEFAULT_SCIENCE_DESIGN, instrument_ids: [...DEFAULT_SCIENCE_DESIGN.instrument_ids] }))
  const [error, setError] = useState('')
  if (!open) return null

  function prepare(): NewJourneyForm | null {
    const date = new Date(start)
    if (!name.trim() || name.trim().length > 55) { setError('Escribe un nombre de 1 a 55 caracteres.'); return null }
    if (!Number.isFinite(date.getTime())) { setError('Selecciona una fecha de lanzamiento válida.'); return null }
    if (!Number.isFinite(durationH) || durationH <= 0 || durationH > 26280) { setError('La duración debe estar entre 0 y 26.280 horas.'); return null }
    if (!Number.isFinite(step) || step <= 0 || durationH * 3600 / step > 30_000) { setError('El paso debe ser positivo y producir como máximo 30.000 pasos.'); return null }
    if (routeKind === 'lunar_free_return' && (!Number.isFinite(minAltitudeKm) || minAltitudeKm < 100 || minAltitudeKm > 20000)) {
      setError('La altitud mínima propuesta debe estar entre 100 y 20.000 km.'); return null
    }
    if (!calculateScienceBudget(science, durationH * 3600).goal_has_required_instrument) { setError('Selecciona el instrumento necesario para el objetivo científico.'); return null }
    if (![...position, ...velocity].every(Number.isFinite)) { setError('Las posiciones y velocidades deben ser números finitos.'); return null }
    setError('')
    const launchIso = date.toISOString()
    return {
      name: name.trim(), launch_iso: launchIso, route_kind: routeKind,
      optimization_goal: optimizationGoal, min_flyby_altitude_km: minAltitudeKm, science: { ...science, instrument_ids: [...science.instrument_ids] }, config: {
        date: launchIso,
        scenario_id: 'earth_moon_circular_v1', duration_s: durationH * 3600, step_s: step,
        initial_state: { position_m: position, velocity_m_s: velocity },
      }
    }
  }
  function submit(kind: 'demo' | 'backend') {
    const data = prepare(); if (!data) return
    if (kind === 'demo') onDemo(data); else onBackend(data)
  }
  function updateVec(kind: 'position' | 'velocity', index: number, v: number) {
    if (kind === 'position') setPosition(old => old.map((x, i) => i === index ? v : x) as [number, number, number])
    else setVelocity(old => old.map((x, i) => i === index ? v : x) as [number, number, number])
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget && !busy) onClose() }}>
    <section className="mission-modal" role="dialog" aria-modal="true" aria-labelledby="create-title">
      <header className="modal-heading"><div><div className="eyebrow">NUEVA EXPLORACIÓN</div><h2 id="create-title">Configura tu viaje</h2><p>Elige un recorrido. El retorno lunar se puede explorar en modo demo.</p></div>
        <button className="icon-button" onClick={onClose} disabled={busy} aria-label="Cerrar formulario"><Icon name="x" /></button>
      </header>
      <div className="modal-content">
        <label className="field"><span>Nombre de la misión</span><input maxLength={55} value={name} onChange={e => setName(e.target.value)} placeholder="Misión 01" /></label>
        <div className="form-section-title">Tipo de misión</div>
        <div className="route-choices" role="radiogroup" aria-label="Tipo de misión">
          <label className={`route-choice ${routeKind === 'earth_moon' ? 'chosen' : ''}`}>
            <input type="radio" name="route-kind" checked={routeKind === 'earth_moon'} onChange={() => setRouteKind('earth_moon')} />
            <span className="route-choice-body"><strong>Tierra → Luna</strong><small>Trayecto de ida (escenario actual)</small></span>
          </label>
          <label className={`route-choice ${routeKind === 'lunar_free_return' ? 'chosen' : ''}`}>
            <input type="radio" name="route-kind" checked={routeKind === 'lunar_free_return'} onChange={() => { setRouteKind('lunar_free_return'); if (durationH === 72) setDurationH(144) }} />
            <span className="route-choice-body"><strong>Tierra → Luna → Tierra</strong><small>Sobrevuelo y retorno libre lunar</small></span>
          </label>
        </div>
        <div className="form-grid">
          <label className="field"><span>Objetivo de búsqueda (futuro)</span>
            <select value={optimizationGoal} onChange={e => setOptimizationGoal(e.target.value as OptimizationGoal)}>
              <option value="fuel">Menor gasto de combustible</option>
              <option value="time">Menor duración</option>
              <option value="safety">Mayor margen de seguridad</option>
            </select>
          </label>
          {routeKind === 'lunar_free_return' && <label className="field"><span>Altitud mínima deseada sobre la Luna (km)</span>
            <input type="number" min="100" max="20000" step="100" value={minAltitudeKm} onChange={e => setMinAltitudeKm(Number(e.target.value))} />
          </label>}
        </div>
        <p className="route-explanation">{routeKind === 'lunar_free_return'
          ? 'En un retorno libre la nave no se detiene en la Luna. La trayectoria debe pasar a una distancia segura y regresar a la Tierra. «Ver demo» solo ilustra ese recorrido, sin cálculos físicos.'
          : 'La primera versión de FastAPI propaga un estado inicial. No encuentra por sí sola la ruta más óptima.'}</p>
        <div className="form-grid">
          <label className="field"><span>Origen</span><input value="Tierra" readOnly title="El escenario v1 sólo contempla Tierra–Luna" /></label>
          <label className="field"><span>Destino</span><input value={routeKind === 'lunar_free_return' ? 'Tierra (vía Luna)' : 'Luna'} readOnly title="Trayectoria configurada" /></label>
          <label className="field"><span>Fecha y hora de salida</span><input type="datetime-local" value={start} onChange={e => setStart(e.target.value)} /></label>
          <label className="field"><span>Duración (horas)</span><input type="number" min="1" max="26280" step="1" value={durationH} onChange={e => setDurationH(Number(e.target.value))} /></label>
          <label className="field"><span>Paso RK2 (segundos)</span><input type="number" min="1" step="1" value={step} onChange={e => setStep(Number(e.target.value))} /></label>
          <label className="field"><span>Escenario</span><input value="earth_moon_circular_v1" readOnly /></label>
        </div>
        <SciencePayloadSelector design={science} duration_s={durationH * 3600} onChange={setScience} />
        <details className="advanced-fields"><summary><Icon name="settings" size={16} />Estado inicial avanzado <span>metros · m/s</span></summary>
          <p>Estas coordenadas son valores de ejemplo. Deben ajustarse al escenario definido por Parri.</p>
          <div className="vector-header">Posición inicial (m)</div>
          <div className="vector-grid">{position.map((v, i) => <label key={i}> {['x', 'y', 'z'][i]}<input type="number" value={v} onChange={e => updateVec('position', i, Number(e.target.value))} /></label>)}</div>
          <div className="vector-header">Velocidad inicial (m/s)</div>
          <div className="vector-grid">{velocity.map((v, i) => <label key={i}> {['vx', 'vy', 'vz'][i]}<input type="number" value={v} onChange={e => updateVec('velocity', i, Number(e.target.value))} /></label>)}</div>
        </details>
        {error && <div className="form-error" role="alert"><Icon name="alert" size={17} />{error}</div>}
        <div className="form-note"><Icon name="info" size={16} /><span>{routeKind === 'lunar_free_return'
          ? 'El retorno libre se muestra solamente como DEMO SINTÉTICA. La versión actual de FastAPI no acepta aún búsquedas de trayectorias de retorno y el objetivo de optimización es informativo.'
          : '«Ver demo» dibuja una ruta inventada. «Simular con Python» propaga el estado inicial con el contrato v1 de Rafa; no optimiza la ruta.'}</span></div>
      </div>
      <footer className="modal-footer">
        <button className="secondary-button" disabled={busy} onClick={() => submit('demo')}><Icon name="orbit" size={17} />Ver demo</button>
        <button className="primary-button" disabled={busy || routeKind === 'lunar_free_return'}
          title={routeKind === 'lunar_free_return' ? 'Pendiente de que el backend admita el retorno libre' : 'Propagar con FastAPI'}
          onClick={() => submit('backend')}><Icon name={busy ? 'clock' : 'rocket'} size={18} />{busy ? 'Calculando...' : 'Simular con Python'}</button>
      </footer>
    </section>
  </div>
}
