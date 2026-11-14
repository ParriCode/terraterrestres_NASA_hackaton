import { useState } from 'react'
import type { FormEvent } from 'react'
import type { OptimizeTransferRequest } from '../types/transfer'
import Icon from './Icon'

const MAX_DAYS = 30 // límite de max_duration_s en el backend
const SAMPLES = 400
const DEFAULT_PARKING_ALT_M = 200_000

type Props = { busy: boolean; onSubmit: (request: OptimizeTransferRequest) => void; onCancel: () => void }

export default function TransferForm({ busy, onSubmit, onCancel }: Props) {
  // datetime-local sin zona: se interpreta explícitamente como UTC
  const [date, setDate] = useState('2026-11-14T00:00')
  const [maxDays, setMaxDays] = useState(10)
  const [error, setError] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const instant = new Date(`${date}:00Z`)
    if (!date || Number.isNaN(instant.getTime())) return setError('Introduce una fecha de salida válida.')
    if (!Number.isFinite(maxDays) || maxDays <= 0 || maxDays > MAX_DAYS) {
      return setError(`El tiempo máximo de vuelo debe estar entre 0 y ${MAX_DAYS} días.`)
    }
    setError('')
    onSubmit({
      date: instant.toISOString(),
      max_duration_s: Math.round(maxDays * 86400),
      parking_alt_m: DEFAULT_PARKING_ALT_M,
      samples: SAMPLES,
    })
  }

  return <form className="transfer-form" onSubmit={submit} noValidate>
    <h2><Icon name="rocket" size={16} />Optimizador Tierra → Luna</h2>
    <label>Fecha de salida (UTC)
      <input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} disabled={busy} required />
    </label>
    <label>Tiempo máximo de vuelo (días)
      <input type="number" min={0.5} max={MAX_DAYS} step={0.5} value={maxDays} onChange={e => setMaxDays(e.target.valueAsNumber)} disabled={busy} />
    </label>
    <div className="assumption-pill">
      <span>Supuesto inicial</span>
      <strong>Órbita circular de aparcamiento: 200 km</strong>
      <small>Minimiza el Δv total estimado · Efemérides NASA/JPL Horizons</small>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy
      ? <div className="form-actions"><span className="loading"><span className="spinner" />Optimizando transferencia…</span>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button></div>
      : <button type="submit" className="primary-button"><Icon name="play" size={14} />Buscar transferencia óptima</button>}
  </form>
}
