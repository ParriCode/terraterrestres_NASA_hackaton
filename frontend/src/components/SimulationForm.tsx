import { useState } from 'react'
import type { SimulationConfig } from '../types/simulation'
import Icon from './Icon'

export type NewJourneyForm = { name: string; launch_iso: string; config: SimulationConfig }
type Props = { open: boolean; busy: boolean; onClose: () => void; onDemo: (data: NewJourneyForm) => void; onBackend: (data: NewJourneyForm) => void }
function toLocal(date: Date) { const pad = (v: number) => String(v).padStart(2, '0'); return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}` }

export default function SimulationForm({ open, busy, onClose, onDemo, onBackend }: Props) {
  const [name, setName] = useState('Misión Artemis')
  const [start, setStart] = useState(() => toLocal(new Date(Date.now() - 12 * 3600_000)))
  const [durationH, setDurationH] = useState(72)
  const [step, setStep] = useState(900)
  const [position, setPosition] = useState<[number, number, number]>([2_001_000, 0, 0])
  const [velocity, setVelocity] = useState<[number, number, number]>([0, 10_800, 0])
  const [error, setError] = useState('')
  if (!open) return null

  function prepare(): NewJourneyForm | null {
    const date = new Date(start)
    if (!name.trim() || name.trim().length > 55) { setError('Escribe un nombre de 1 a 55 caracteres.'); return null }
    if (!Number.isFinite(date.getTime())) { setError('Selecciona una fecha de lanzamiento válida.'); return null }
    if (!Number.isFinite(durationH) || durationH <= 0 || durationH > 26280) { setError('La duración debe estar entre 0 y 26.280 horas.'); return null }
    if (!Number.isFinite(step) || step <= 0 || durationH * 3600 / step > 30_000) { setError('El paso debe ser positivo y producir como máximo 30.000 pasos.'); return null }
    if (![...position, ...velocity].every(Number.isFinite)) { setError('Las posiciones y velocidades deben ser números finitos.'); return null }
    setError('')
    return {
      name: name.trim(), launch_iso: date.toISOString(), config: {
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
      <header className="modal-heading"><div><div className="eyebrow">NUEVA EXPLORACIÓN</div><h2 id="create-title">Configura tu viaje</h2><p>Por ahora el contrato científico admite Tierra–Luna.</p></div>
        <button className="icon-button" onClick={onClose} disabled={busy} aria-label="Cerrar formulario"><Icon name="x" /></button>
      </header>
      <div className="modal-content">
        <label className="field"><span>Nombre de la misión</span><input maxLength={55} value={name} onChange={e => setName(e.target.value)} placeholder="Misión 01" /></label>
        <div className="form-grid">
          <label className="field"><span>Origen</span><input value="Tierra" readOnly title="El escenario v1 sólo contempla Tierra–Luna" /></label>
          <label className="field"><span>Destino</span><input value="Luna" readOnly title="El escenario v1 sólo contempla Tierra–Luna" /></label>
          <label className="field"><span>Fecha y hora de salida</span><input type="datetime-local" value={start} onChange={e => setStart(e.target.value)} /></label>
          <label className="field"><span>Duración (horas)</span><input type="number" min="1" max="26280" step="1" value={durationH} onChange={e => setDurationH(Number(e.target.value))} /></label>
          <label className="field"><span>Paso RK2 (segundos)</span><input type="number" min="1" step="1" value={step} onChange={e => setStep(Number(e.target.value))} /></label>
          <label className="field"><span>Escenario</span><input value="earth_moon_circular_v1" readOnly /></label>
        </div>
        <details className="advanced-fields"><summary><Icon name="settings" size={16} />Estado inicial avanzado <span>metros · m/s</span></summary>
          <p>Estas coordenadas son valores de ejemplo. Deben ajustarse al escenario definido por Parri.</p>
          <div className="vector-header">Posición inicial (m)</div>
          <div className="vector-grid">{position.map((v, i) => <label key={i}> {['x', 'y', 'z'][i]}<input type="number" value={v} onChange={e => updateVec('position', i, Number(e.target.value))} /></label>)}</div>
          <div className="vector-header">Velocidad inicial (m/s)</div>
          <div className="vector-grid">{velocity.map((v, i) => <label key={i}> {['vx', 'vy', 'vz'][i]}<input type="number" value={v} onChange={e => updateVec('velocity', i, Number(e.target.value))} /></label>)}</div>
        </details>
        {error && <div className="form-error" role="alert"><Icon name="alert" size={17} />{error}</div>}
        <div className="form-note"><Icon name="info" size={16} /><span>«Ver demo» dibuja una ruta inventada para probar React. «Simular con Python» solicita datos auténticos al endpoint de Rafa.</span></div>
      </div>
      <footer className="modal-footer">
        <button className="secondary-button" disabled={busy} onClick={() => submit('demo')}><Icon name="orbit" size={17} />Ver demo</button>
        <button className="primary-button" disabled={busy} onClick={() => submit('backend')}><Icon name={busy ? 'clock' : 'rocket'} size={18} />{busy ? 'Calculando...' : 'Simular con Python'}</button>
      </footer>
    </section>
  </div>
}
