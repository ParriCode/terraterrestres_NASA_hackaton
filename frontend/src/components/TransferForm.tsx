import { useState } from 'react'
import type { FormEvent } from 'react'
import type { MissionProfile, MissionSubmitPayload } from '../types/transfer'
import Icon from './Icon'

const SAMPLES = 400
const DEFAULT_PARKING_ALT_M = 200_000

type Props = {
  busy: boolean
  onSubmit: (request: MissionSubmitPayload) => void
  onCancel: () => void
}

export default function TransferForm({ busy, onSubmit, onCancel }: Props) {
  const [profile, setProfile] = useState<MissionProfile>('one_way')
  const [date, setDate] = useState('2026-11-14T00:00')
  const [maxDays, setMaxDays] = useState(10)
  const [lunarPeriAltKm, setLunarPeriAltKm] = useState(150)
  const [lunarStayHours, setLunarStayHours] = useState(24)
  const [reentryAltKm, setReentryAltKm] = useState(120)
  const [error, setError] = useState('')

  const maxAllowedDays = profile === 'one_way' ? 30 : 35

  function handleProfileChange(next: MissionProfile) {
    setProfile(next)
    setError('')
    if (next === 'one_way' && maxDays > 30) setMaxDays(10)
    if (next === 'free_return' && maxDays < 10) setMaxDays(12)
    if (next === 'lunar_orbit' && maxDays < 12) setMaxDays(14)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const instant = new Date(`${date}:00Z`)
    if (!date || Number.isNaN(instant.getTime())) {
      return setError('Introduce una fecha de salida válida.')
    }
    if (!Number.isFinite(maxDays) || maxDays <= 0 || maxDays > maxAllowedDays) {
      return setError(`El tiempo máximo debe estar entre 0 y ${maxAllowedDays} días.`)
    }

    if (profile === 'one_way') {
      setError('')
      return onSubmit({
        kind: 'one_way',
        payload: {
          date: instant.toISOString(),
          max_duration_s: Math.round(maxDays * 86400),
          parking_alt_m: DEFAULT_PARKING_ALT_M,
          samples: SAMPLES,
        },
      })
    }

    if (!Number.isFinite(lunarPeriAltKm) || lunarPeriAltKm < 20 || lunarPeriAltKm > 10_000) {
      return setError('La altitud de perilunio debe estar entre 20 y 10 000 km.')
    }
    if (!Number.isFinite(reentryAltKm) || reentryAltKm < 50 || reentryAltKm > 1000) {
      return setError('La altitud de reentrada debe estar entre 50 y 1000 km.')
    }
    if (profile === 'lunar_orbit' && (!Number.isFinite(lunarStayHours) || lunarStayHours < 0 || lunarStayHours > 336)) {
      return setError('La estancia lunar debe estar entre 0 y 336 horas.')
    }

    setError('')
    onSubmit({
      kind: 'round_trip',
      payload: {
        date: instant.toISOString(),
        mode: profile,
        max_total_duration_s: Math.round(maxDays * 86400),
        parking_alt_m: DEFAULT_PARKING_ALT_M,
        lunar_periapsis_alt_m: Math.round(lunarPeriAltKm * 1000),
        lunar_stay_s: profile === 'lunar_orbit' ? Math.round(lunarStayHours * 3600) : 0,
        reentry_alt_m: Math.round(reentryAltKm * 1000),
        samples: SAMPLES,
      },
    })
  }

  return (
    <form className="transfer-form" onSubmit={submit} noValidate>
      <h2><Icon name="rocket" size={16} />Planificador Tierra–Luna</h2>

      <label>
        Perfil de misión
        <select
          value={profile}
          onChange={e => handleProfileChange(e.target.value as MissionProfile)}
          disabled={busy}
        >
          <option value="one_way">Tierra → Luna (Solo ida)</option>
          <option value="free_return">Tierra → Luna → Tierra · Retorno libre (Apolo 8/13)</option>
          <option value="lunar_orbit">Tierra → Luna → Tierra · Órbita lunar (Apolo 11)</option>
        </select>
      </label>

      <label>
        Fecha de salida (UTC)
        <input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} disabled={busy} required />
      </label>

      <label>
        {profile === 'one_way' ? 'Tiempo máximo de vuelo (días)' : 'Duración máxima total de misión (días)'}
        <input
          type="number"
          min={0.5}
          max={maxAllowedDays}
          step={0.5}
          value={maxDays}
          onChange={e => setMaxDays(e.target.valueAsNumber)}
          disabled={busy}
        />
      </label>

      {profile !== 'one_way' && (
        <>
          <label>
            Altitud mínima sobre la Luna (km)
            <input
              type="number"
              min={20}
              max={10000}
              step={10}
              value={lunarPeriAltKm}
              onChange={e => setLunarPeriAltKm(e.target.valueAsNumber)}
              disabled={busy}
            />
          </label>

          {profile === 'lunar_orbit' && (
            <label>
              Estancia en órbita lunar (horas)
              <input
                type="number"
                min={0}
                max={336}
                step={2}
                value={lunarStayHours}
                onChange={e => setLunarStayHours(e.target.valueAsNumber)}
                disabled={busy}
              />
            </label>
          )}

          <label>
            Altitud de reentrada terrestre (km)
            <input
              type="number"
              min={50}
              max={1000}
              step={10}
              value={reentryAltKm}
              onChange={e => setReentryAltKm(e.target.valueAsNumber)}
              disabled={busy}
            />
          </label>
        </>
      )}

      <div className="assumption-pill">
        <span>Modelo físico</span>
        <strong>Órbita de aparcamiento: 200 km · 4 cuerpos (Tierra, Luna, Sol, Nave)</strong>
        <small>
          {profile === 'one_way'
            ? 'Minimiza Δv total estimado · Efemérides NASA/JPL Horizons'
            : profile === 'free_return'
              ? 'Encendido único TLI con asistencia gravitatoria lunar de regreso'
              : 'TLI + inserción en órbita lunar (LOI) + retorno transterrestre (TEI)'}
        </small>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      {busy ? (
        <div className="form-actions">
          <span className="loading"><span className="spinner" />Calculando trayectoria…</span>
          <button type="button" className="ghost-button" onClick={onCancel}>Cancelar</button>
        </div>
      ) : (
        <button type="submit" className="primary-button">
          <Icon name="play" size={14} />
          {profile === 'one_way' ? 'Buscar transferencia óptima' : 'Calcular misión de ida y vuelta'}
        </button>
      )}
    </form>
  )
}