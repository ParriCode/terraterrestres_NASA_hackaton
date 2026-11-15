import { useState } from 'react'
import type { FormEvent } from 'react'
import type { MissionMode, TransferObjective, TransferRequest } from '../types/transfer'
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
  const [objective, setObjective] = useState<TransferObjective>('energia')
  const [missionMode, setMissionMode] = useState<MissionMode>('lunar_transfer')
  const [orbitAltitudeKm, setOrbitAltitudeKm] = useState('100')
  const [lunarRevolutions, setLunarRevolutions] = useState<1 | 2>(1)
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

    const altitude = Number(orbitAltitudeKm)
    if (missionMode === 'lunar_orbit_return' && (durationDays < 4 || !Number.isFinite(altitude) || altitude < 50 || altitude > 500)) {
      return setError('Para orbitar y regresar, usa 4 a 30 días y una órbita de 50 a 500 km de altitud.')
    }
    setError('')
    onSubmit({
      mission_mode: missionMode,
      ...(missionMode === 'lunar_orbit_return' ? { orbit_altitude_km: altitude, lunar_revolutions: lunarRevolutions } : {}),
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
    <h2><Icon name="rocket" size={16} />Configura tu misión lunar</h2>
    <p className="form-description">Elige el recorrido, la duración, la masa y el objetivo. La órbita lunar requiere maniobras propulsadas.</p>
    <fieldset disabled={busy}>
      <legend>Tipo de misión</legend>
      <div className="segmented">
        <button type="button" aria-pressed={missionMode === 'lunar_transfer'} className={missionMode === 'lunar_transfer' ? 'active' : ''}
          onClick={() => setMissionMode('lunar_transfer')}>Tierra → Luna</button>
        <button type="button" aria-pressed={missionMode === 'lunar_orbit_return'} className={missionMode === 'lunar_orbit_return' ? 'active' : ''}
          onClick={() => setMissionMode('lunar_orbit_return')}>Órbita lunar y regreso</button>
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
    <label>{missionMode === 'lunar_orbit_return' ? 'Duración máxima (días)' : 'Duración (días)'}
      <input type="number" min="0.5" max={MAX_DAYS} step="0.5" value={days} onChange={e => setDays(e.target.value)} disabled={busy} required />
    </label>
    {missionMode === 'lunar_orbit_return' && <>
      <label>Altitud orbital lunar (km)
        <input type="number" min="50" max="500" step="10" value={orbitAltitudeKm}
          onChange={e => setOrbitAltitudeKm(e.target.value)} disabled={busy} required />
      </label>
      <fieldset disabled={busy}>
        <legend>Vueltas a la Luna</legend>
        <div className="segmented">
          <button type="button" className={lunarRevolutions === 1 ? 'active' : ''} aria-pressed={lunarRevolutions === 1} onClick={() => setLunarRevolutions(1)}>1 vuelta</button>
          <button type="button" className={lunarRevolutions === 2 ? 'active' : ''} aria-pressed={lunarRevolutions === 2} onClick={() => setLunarRevolutions(2)}>2 vueltas</button>
        </div>
      </fieldset>
    </>}
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
    <p className="form-note">{missionMode === 'lunar_orbit_return'
      ? 'Inserción orbital, una o dos revoluciones y retorno antes del límite de días indicado. La misión termina al entrar en la esfera terrestre de 100.000 km; no se simula reentrada ni aterrizaje.'
      : 'El ángulo de llegada se busca automáticamente entre alternativas válidas. La duración es fija.'}</p>
    <details className="technical-details"><summary>Alcance de la búsqueda</summary>
      <p>La salida técnica es de 90°. La búsqueda es acotada y no garantiza un óptimo global. Para orbitar y regresar se calculan dos impulsos (captura y salida) sin consumo de combustible modelado; la masa escala la energía, pero no altera trayectorias sin empuje.</p>
    </details>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy
      ? <div className="form-actions"><span className="loading"><img src="/resource/loading_cohete_nubes.svg" alt="" />Calculando misión…</span>
        <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button></div>
      : <button type="submit" className="primary-button"><Icon name="play" size={14} />Calcular misión</button>}
  </form>
}
