import { useEffect, useRef } from 'react'
import type { TransferRequest } from '../types/transfer'
import { bodyName } from '../data/solarSystem'
import Icon from './Icon'

type Props = { request: TransferRequest; detail: string; onRevise: (field?: 'date' | 'duration') => void }

export default function MissionFailure({ request, detail, onRevise }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = dialog.current
    node?.showModal()
    return () => node?.close()
  }, [])
  const date = new Date(request.date).toLocaleString('es-ES', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' })
  return <dialog ref={dialog} className="mission-failure" aria-labelledby="mission-failure-title" aria-describedby="mission-failure-description"
    onCancel={e => { e.preventDefault(); onRevise() }}>
    <button type="button" className="failure-close icon-button" onClick={() => onRevise()} aria-label="Cerrar aviso y revisar misión"><Icon name="x" /></button>
    <MissedTrajectory origin={bodyName(request.origin_id ?? 'earth')} destination={bodyName(request.destination_id ?? 'moon')} />
    <p className="failure-eyebrow">BÚSQUEDA SIN RESULTADO</p>
    <h2 id="mission-failure-title">No se encontró una ruta válida</h2>
    <p id="mission-failure-description">Con esta fecha y duración, la búsqueda no ha encontrado una trayectoria que cumpla las condiciones de llegada.</p>
    <div className="failure-trip">
      <strong>{bodyName(request.origin_id ?? 'earth')} <span aria-hidden="true">→</span> {bodyName(request.destination_id ?? 'moon')}</strong>
      <span>{date} UTC · {(request.duration_s / 86400).toLocaleString('es-ES')} días</span>
      {request.mission_mode === 'lunar_orbit_return' && <span>Órbita lunar y regreso</span>}
    </div>
    <p className="failure-hint">Prueba otra duración o fecha de salida. La búsqueda es limitada: este resultado no significa que el viaje sea imposible.</p>
    <div className="failure-actions">
      <button autoFocus type="button" className="primary-button" onClick={() => onRevise('duration')}><Icon name="clock" size={17} />Cambiar duración</button>
      <button type="button" className="ghost-button" onClick={() => onRevise('date')}>Cambiar fecha</button>
    </div>
    <details className="failure-details"><summary>Ver detalle de la búsqueda</summary><p>{detail}</p></details>
  </dialog>
}

function MissedTrajectory({ origin, destination }: { origin: string; destination: string }) {
  return <svg className="failure-visual" viewBox="0 0 460 170" role="img" aria-label={`Trayectoria de ${origin} a ${destination} que no alcanza el destino`}>
    <defs>
      <radialGradient id="mf-origin"><stop offset="0" stopColor="#7cc4ff" /><stop offset="1" stopColor="#2b6cb0" /></radialGradient>
      <radialGradient id="mf-dest"><stop offset="0" stopColor="#e6e9ef" /><stop offset="1" stopColor="#7d8796" /></radialGradient>
    </defs>
    {Array.from({ length: 18 }, (_, i) => <circle key={i} cx={(i * 97) % 460} cy={(i * 53) % 170} r={i % 3 ? 0.8 : 1.3} fill="#ffffff55" />)}
    <circle cx="380" cy="70" r="34" className="mf-target-ring" />
    <circle cx="380" cy="70" r="20" fill="url(#mf-dest)" />
    <circle cx="70" cy="110" r="26" fill="url(#mf-origin)" />
    <path id="mf-path" d="M96 104 C 190 40, 290 10, 420 150" className="mf-path" />
    <path d="M96 104 C 190 40, 290 10, 420 150" className="mf-path-glow" />
    <g className="mf-ship"><circle r="5" fill="#ffbd69" /><animateMotion dur="3.2s" repeatCount="indefinite" path="M96 104 C 190 40, 290 10, 420 150" /></g>
    <g className="mf-miss" transform="translate(420 150)"><line x1="-8" y1="-8" x2="8" y2="8" /><line x1="8" y1="-8" x2="-8" y2="8" /></g>
    <text x="70" y="156" textAnchor="middle">{origin}</text>
    <text x="380" y="24" textAnchor="middle">{destination}</text>
  </svg>
}
