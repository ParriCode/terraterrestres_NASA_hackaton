import { useState } from 'react'
import type { FormEvent } from 'react'
import type { TransferObjective, TransferRequest } from '../types/transfer'
import Icon from './Icon'

/**
 * Compatibilidad con POST /transfers actual: el backend aún necesita horizonte
 * y geometría explícitos. NO ES una búsqueda automática del tiempo óptimo.
 */
const FIXED_DURATION_S = 10 * 86400
const FIXED_LAUNCH_ANGLE_DEG = 90
const FIXED_ARRIVAL_ANGLE_DEG = 0
const SAMPLES = 400

function utcNowForInput(): string { return new Date().toISOString().slice(0, 16) }
type Props = { busy: boolean; onSubmit: (request: TransferRequest) => void; onCancel: () => void }

export default function TransferForm({ busy, onSubmit, onCancel }: Props) {
  // La entrada se interpreta explícitamente como UTC al serializar (no como huso horario local).
  const [date, setDate] = useState(utcNowForInput)
  const [mass, setMass] = useState('1000')
  const [objective, setObjective] = useState<TransferObjective>('energia')
  const [error, setError] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!date) return setError('Introduce una fecha de salida UTC válida.')
    const instant = new Date(`${date}:00Z`)
    if (!Number.isFinite(instant.getTime())) return setError('La fecha de salida no es válida.')
    const massKg = Number(mass)
    if (!mass.trim() || !Number.isFinite(massKg) || massKg <= 0) return setError('La masa debe ser un número positivo en kg.')
    setError('')
    onSubmit({
      date: instant.toISOString(), objective, mass_kg: massKg, samples: SAMPLES,
      duration_s: FIXED_DURATION_S,
      launch_angle_deg: FIXED_LAUNCH_ANGLE_DEG,
      arrival_angle_deg: FIXED_ARRIVAL_ANGLE_DEG,
    })
  }

  return <form className="transfer-form" onSubmit={submit} noValidate>
    <h2><Icon name="rocket" size={16} />Crear transferencia Tierra → Luna</h2>
    <p className="form-description">Elige la fecha, la masa de la nave y qué criterio quieres priorizar.</p>
    <label>Fecha de salida (UTC)
      <input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} disabled={busy} required />
    </label>
    <label>Masa de la nave (kg)
      <input type="number" min="0.001" step="any" value={mass} onChange={e => setMass(e.target.value)} disabled={busy} required />
    </label>
    <fieldset disabled={busy}>
      <legend>Objetivo</legend>
      <div className="segmented">
        <button type="button" aria-pressed={objective === 'energia'} className={objective === 'energia' ? 'active' : ''}
          onClick={() => setObjective('energia')}>Mínima energía</button>
        <button type="button" aria-pressed={objective === 'distancia'} className={objective === 'distancia' ? 'active' : ''}
          onClick={() => setObjective('distancia')}>Mínima distancia</button>
      </div>
    </fieldset>
    <p className="form-note">La masa modifica la energía total en J, no la trayectoria gravitatoria de una nave sin empuje.</p>
    <details className="technical-details"><summary>Alcance científico de la búsqueda</summary>
      <p>El backend actual busca candidatos para 10 días y geometría fija (90° de salida, 0° de llegada). La duración óptima automática todavía requiere una ampliación en Python. No se garantiza el óptimo global.</p>
    </details>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy
      ? <div className="form-actions"><span className="loading"><img src="/resource/loading_cohete_nubes.svg" alt="" />Calculando…</span>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button></div>
      : <button type="submit" className="primary-button"><Icon name="play" size={14} />Calcular transferencia</button>}
  </form>
}
