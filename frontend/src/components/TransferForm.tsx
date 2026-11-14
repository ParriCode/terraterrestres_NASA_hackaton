import { useState } from 'react'
import type { FormEvent } from 'react'
import type { TransferObjective, TransferRequest } from '../types/transfer'
import Icon from './Icon'

/** La fecha se interpreta como UTC y la duración se envía en segundos. */
const FIXED_LAUNCH_ANGLE_DEG = 90
const SAMPLES = 400
const SECONDS_PER_DAY = 86400
const MAX_DAYS = 30 // backend/app/controllers/transfer_controller.py

function utcNowForInput(): string { return new Date().toISOString().slice(0, 16) }
type Props = { busy: boolean; onSubmit: (request: TransferRequest) => void; onCancel: () => void }

export default function TransferForm({ busy, onSubmit, onCancel }: Props) {
  const [date, setDate] = useState(utcNowForInput)
  const [days, setDays] = useState('10')
  const [mass, setMass] = useState('1000')
  const [objective, setObjective] = useState<TransferObjective>('energia')
  const [error, setError] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!date) return setError('Introduce una fecha de salida UTC válida.')
    const instant = new Date(`${date}:00Z`)
    if (!Number.isFinite(instant.getTime())) return setError('La fecha de salida no es válida.')

    const durationDays = Number(days)
    if (!days.trim() || !Number.isFinite(durationDays) || durationDays <= 0 || durationDays > MAX_DAYS) {
      return setError(`La duración debe ser mayor que 0 y como máximo ${MAX_DAYS} días.`)
    }
    const massKg = Number(mass)
    if (!mass.trim() || !Number.isFinite(massKg) || massKg <= 0) {
      return setError('La masa debe ser un número positivo en kg.')
    }

    setError('')
    onSubmit({
      date: instant.toISOString(),
      duration_s: durationDays * SECONDS_PER_DAY,
      launch_angle_deg: FIXED_LAUNCH_ANGLE_DEG,
      objective,
      mass_kg: massKg,
      samples: SAMPLES,
      // NO enviamos arrival_angle_deg: el endpoint optimizado debe buscarlo.
    })
  }

  return <form className="transfer-form" onSubmit={submit} noValidate>
    <h2><Icon name="rocket" size={16} />Crear transferencia Tierra → Luna</h2>
    <p className="form-description">Elige la fecha, los días de vuelo, la masa y el criterio que prefieres optimizar.</p>
    <label>Fecha de salida (UTC)
      <input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} disabled={busy} required />
    </label>
    <label>Duración (días)
      <input type="number" min="0.5" max={MAX_DAYS} step="0.5" value={days} onChange={e => setDays(e.target.value)} disabled={busy} required />
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
    <p className="form-note">El ángulo de llegada se busca automáticamente entre las alternativas físicamente válidas. La duración elegida es fija durante esa búsqueda.</p>
    <details className="technical-details"><summary>Alcance de la búsqueda</summary>
      <p>Se mantiene una salida técnica de 90°. El backend debe elegir el mejor ángulo de llegada entre los candidatos que evalúe. La búsqueda no garantiza un óptimo global. La masa cambia la energía de lanzamiento (J), no la trayectoria gravitatoria de la nave sin empuje.</p>
    </details>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy
      ? <div className="form-actions"><span className="loading"><img src="/resource/loading_cohete_nubes.svg" alt="" />Buscando transferencia…</span>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button></div>
      : <button type="submit" className="primary-button"><Icon name="play" size={14} />Buscar mejor transferencia</button>}
  </form>
}
