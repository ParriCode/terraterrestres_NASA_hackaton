import { useState } from 'react'
import type { FormEvent } from 'react'
import type { TransferObjective, TransferRequest } from '../types/transfer'
import Icon from './Icon'

const MAX_DAYS = 30 // límite de duration_s en el backend
const SAMPLES = 400
const MASS_KG = 1

type Props = { busy: boolean; onSubmit: (request: TransferRequest) => void; onCancel: () => void }

export default function TransferForm({ busy, onSubmit, onCancel }: Props) {
  // datetime-local sin zona: se interpreta explícitamente como UTC
  const [date, setDate] = useState('2026-11-14T00:00')
  const [days, setDays] = useState(10)
  const [launchAngle, setLaunchAngle] = useState(90)
  const [arrivalAngle, setArrivalAngle] = useState(0)
  const [objective, setObjective] = useState<TransferObjective>('energia')
  const [error, setError] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const instant = new Date(`${date}:00Z`)
    if (!date || Number.isNaN(instant.getTime())) return setError('Introduce una fecha de salida válida.')
    if (!Number.isFinite(days) || days <= 0 || days > MAX_DAYS) return setError(`La duración debe estar entre 0 y ${MAX_DAYS} días.`)
    if (!Number.isFinite(launchAngle) || !Number.isFinite(arrivalAngle)) return setError('Los ángulos deben ser números.')
    setError('')
    onSubmit({
      date: instant.toISOString(), duration_s: Math.round(days * 86400),
      launch_angle_deg: launchAngle, arrival_angle_deg: arrivalAngle,
      objective, mass_kg: MASS_KG, samples: SAMPLES,
    })
  }

  return <form className="transfer-form" onSubmit={submit} noValidate>
    <h2><Icon name="rocket" size={16} />Transferencia Tierra → Luna</h2>
    <label>Fecha de salida (UTC)
      <input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} disabled={busy} required />
    </label>
    <label>Duración (días)
      <input type="number" min={0.5} max={MAX_DAYS} step={0.5} value={days} onChange={e => setDays(e.target.valueAsNumber)} disabled={busy} />
    </label>
    <div className="form-row">
      <label title="Ángulo desde la dirección Tierra→Luna">Ángulo salida (°)
        <input type="number" step={1} value={launchAngle} onChange={e => setLaunchAngle(e.target.valueAsNumber)} disabled={busy} />
      </label>
      <label title="Ángulo desde la dirección Luna→Tierra">Ángulo llegada (°)
        <input type="number" step={1} value={arrivalAngle} onChange={e => setArrivalAngle(e.target.valueAsNumber)} disabled={busy} />
      </label>
    </div>
    <fieldset disabled={busy}>
      <legend>Objetivo</legend>
      <div className="segmented">
        <button type="button" className={objective === 'energia' ? 'active' : ''} onClick={() => setObjective('energia')}>Mínima energía</button>
        <button type="button" className={objective === 'distancia' ? 'active' : ''} onClick={() => setObjective('distancia')}>Mínima distancia</button>
      </div>
    </fieldset>
    <p className="form-note">Masa fija: {MASS_KG} kg · Efemérides NASA/JPL Horizons</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy
      ? <div className="form-actions"><span className="loading"><span className="spinner" />Calculando transferencia…</span>
          <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button></div>
      : <button type="submit" className="primary-button"><Icon name="play" size={14} />Calcular transferencia</button>}
  </form>
}
