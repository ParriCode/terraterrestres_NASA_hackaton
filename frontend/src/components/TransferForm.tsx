import { useState } from 'react'
import type { FormEvent } from 'react'
import type { MissionMode, TransferRequest } from '../types/transfer'
import Icon from './Icon'

/** La fecha se interpreta como UTC y la duración se envía en segundos. */
const FIXED_LAUNCH_ANGLE_DEG = 90
const SAMPLES = 400
const SECONDS_PER_DAY = 86400
const MAX_DAYS = 30 // backend/app/controllers/transfer_controller.py

function utcNowForInput(): string { return new Date().toISOString().slice(0, 16) }
type Props = { busy: boolean; onSubmit: (request: TransferRequest) => void; onCancel: () => void; onDateChange?: (date: Date) => void }

export default function TransferForm({ busy, onSubmit, onCancel, onDateChange }: Props) {
  const [date, setDate] = useState(utcNowForInput)
  const [days, setDays] = useState('10')
  const [mass, setMass] = useState('1000')
  const [missionMode, setMissionMode] = useState<MissionMode>('lunar_transfer')
  const [orbitAltitudeKm, setOrbitAltitudeKm] = useState('100')
  const [lunarStayHours, setLunarStayHours] = useState('6')
  const [error, setError] = useState('')
  const isReturn = missionMode !== 'lunar_transfer'

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!date) return setError('Introduce una fecha de salida UTC válida.')
    const instant = new Date(`${date}:00Z`)
    if (!Number.isFinite(instant.getTime())) return setError('La fecha de salida no es válida.')

    const durationDays = Number(days)
    if (!days.trim() || !Number.isFinite(durationDays) || durationDays <= 0 || durationDays > (isReturn ? 35 : MAX_DAYS)) {
      return setError(`La duración debe ser mayor que 0 y como máximo ${isReturn ? 35 : MAX_DAYS} días.`)
    }
    if (isReturn && durationDays < 6) return setError('Para un retorno, introduce al menos 6 días; la búsqueda necesita una ventana suficiente.')
    const massKg = Number(mass)
    if (!mass.trim() || !Number.isFinite(massKg) || massKg <= 0) {
      return setError('La masa debe ser un número positivo en kg.')
    }

    const altitude = Number(orbitAltitudeKm)
    if (missionMode === 'lunar_orbit_return' && (durationDays < 4 || !Number.isFinite(altitude) || altitude < 50 || altitude > 500)) {
      return setError('Para orbitar y regresar, usa al menos 6 días y una órbita de 50 a 500 km de altitud.')
    }
    const stayHours = Number(lunarStayHours)
    if (missionMode === 'lunar_orbit_return') {
      if (!lunarStayHours.trim() || !Number.isFinite(stayHours) || stayHours < 0.5 || stayHours > 336) {
        return setError('Introduce una estancia lunar entre 0,5 y 336 horas (14 días).')
      }
      if (durationDays * 24 < 5.5 * 24 + stayHours) {
        return setError('La duración máxima debe permitir la estancia lunar más al menos 5,5 días para ida y regreso.')
      }
    }
    setError('')
    onSubmit({
      mission_mode: missionMode,
      ...(missionMode === 'lunar_orbit_return' ? { orbit_altitude_km: altitude, lunar_stay_s: stayHours * 3600 } : {}),
      date: instant.toISOString(),
      duration_s: durationDays * SECONDS_PER_DAY,
      launch_angle_deg: FIXED_LAUNCH_ANGLE_DEG,
      objective: 'energia',
      mass_kg: massKg,
      samples: SAMPLES,
    })
  }

  return <form className="transfer-form" onSubmit={submit} noValidate>
    <h2><Icon name="rocket" size={16} />Configura tu misión lunar</h2>
    <p className="form-description">Elige el recorrido, la duración y la masa. La órbita lunar requiere maniobras propulsadas.</p>
    <fieldset disabled={busy}>
      <legend>Tipo de misión</legend>
      <div className="segmented mission-modes">
        <button type="button" aria-pressed={missionMode === 'lunar_transfer'} className={missionMode === 'lunar_transfer' ? 'active' : ''}
          onClick={() => setMissionMode('lunar_transfer')}>Transferencia directa</button>
        <button type="button" aria-pressed={missionMode === 'free_return'} className={missionMode === 'free_return' ? 'active' : ''}
          onClick={() => setMissionMode('free_return')}>Apolo 8/13</button>
        <button type="button" aria-pressed={missionMode === 'lunar_orbit_return'} className={missionMode === 'lunar_orbit_return' ? 'active' : ''}
          onClick={() => setMissionMode('lunar_orbit_return')}>Apolo 11</button>
      </div>
    </fieldset>
    <label>Fecha de salida (UTC)
      <input type="datetime-local" value={date} onChange={e => {
        const value = e.target.value
        setDate(value)
        if (value) {
          const next = new Date(`${value}:00Z`)
          if (Number.isFinite(next.getTime())) onDateChange?.(next)
        }
      }} disabled={busy} required />
    </label>
    <label>{isReturn ? 'Duración máxima (días)' : 'Duración (días)'}
      <input type="number" min={isReturn ? '6' : '0.5'} max={isReturn ? 35 : MAX_DAYS} step="0.5" value={days} onChange={e => setDays(e.target.value)} disabled={busy} required />
    </label>
    {missionMode === 'lunar_orbit_return' && <>
      <label>Altitud orbital lunar (km)
        <input type="number" min="50" max="500" step="10" value={orbitAltitudeKm}
          onChange={e => setOrbitAltitudeKm(e.target.value)} disabled={busy} required />
      </label>
      <label>Tiempo en órbita lunar (horas)
        <input type="number" min="0.5" max="336" step="0.5"
          value={lunarStayHours} onChange={e => setLunarStayHours(e.target.value)}
          disabled={busy} required />
        <small className="form-help">La estancia es un tiempo fijo. Las vueltas resultantes dependen de la altitud orbital y se calculan a partir de la trayectoria.</small>
      </label>
    </>}
    <label>Masa de la nave (kg)
      <input type="number" min="0.001" step="any" value={mass} onChange={e => setMass(e.target.value)} disabled={busy} required />
    </label>
    <p className="form-note">{missionMode === 'lunar_orbit_return'
      ? 'Perfil Apolo 11: inserción en órbita lunar, estancia durante el tiempo indicado y regreso. Sin alunizaje ni aterrizaje simulado.'
      : missionMode === 'free_return'
        ? 'Perfil Apolo 8/13: retorno libre alrededor de la Luna, inspirado especialmente en la trayectoria de emergencia del Apolo 13. No es una reconstrucción histórica exacta.'
        : 'El ángulo de llegada se busca automáticamente entre alternativas válidas. La duración es fija.'}</p>
    <details className="technical-details"><summary>Alcance de la búsqueda</summary>
      <p>{isReturn ? 'El motor utiliza efemérides NASA/JPL, Lambert, corrección de disparo y propagación SciPy solve_ivp (no RK2). Se exige llegada entrante al corredor terrestre a 120 km. Sin modelo atmosférico, sin aterrizaje ni combustible por defecto.' : 'Se buscan duraciones y geometrías candidatas hasta el máximo solicitado; no se garantiza un óptimo global.'}</p>
    </details>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy
      ? <div className="form-actions"><span className="loading"><img src="/resource/loading_cohete_nubes.svg" alt="" />Calculando misión…</span>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button></div>
      : <button type="submit" className="primary-button"><Icon name="play" size={14} />Calcular misión</button>}
  </form>
}
