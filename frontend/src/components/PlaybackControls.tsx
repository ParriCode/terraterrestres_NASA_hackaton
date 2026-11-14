import type { CSSProperties } from 'react'
import type { Journey } from '../types/simulation'
import { clamp, elapsedAt, formatDuration } from '../utils/trajectory'
import Icon from './Icon'

export type TimeMode = 'live' | 'manual'
type Props = {
  date: Date; mode: TimeMode; onMode: (mode: TimeMode) => void; journey: Journey | null;
  playing: boolean; onToggle: () => void; speed: number; onSpeed: (v: number) => void; onDate: (d: Date) => void; onReset: () => void; onDeselect: () => void
}
function localInput(date: Date) { const pad = (v: number) => String(v).padStart(2, '0'); return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}` }

export default function PlaybackControls({ date, mode, onMode, journey, playing, onToggle, speed, onSpeed, onDate, onReset, onDeselect }: Props) {
  const start = journey ? new Date(journey.launch_iso).getTime() : date.getTime()
  const max = journey?.result.diagnostics.final_time_s ?? 0
  const elapsed = journey ? elapsedAt(journey, date) : 0
  const current = clamp(elapsed, 0, max)
  return <div className="playback-shell">
    <div className="playback-upper">
      <div className="playback-title"><Icon name="clock" size={16} /><span>LÍNEA TEMPORAL</span></div>
      <div className="playback-header-actions"><div className="time-mode-buttons" role="group" aria-label="Modo de tiempo">
        <button className={mode === 'live' ? 'active' : ''} onClick={() => onMode('live')}><span className="pulse-dot" />Ahora</button>
        <button className={mode === 'manual' ? 'active' : ''} onClick={() => onMode('manual')}><Icon name="calendar" size={14} />Fecha</button>
      </div><button className="playback-close" onClick={onDeselect} aria-label="Deseleccionar misión y ocultar línea temporal" title="Cerrar línea temporal"><Icon name="x" size={14} /></button></div>
    </div>
    <div className="playback-main">
      <button className="play-main-button" onClick={onToggle} disabled={!journey || mode === 'live'} title={playing ? 'Pausar' : 'Reproducir'} aria-label={playing ? 'Pausar' : 'Reproducir'}><Icon name={playing ? 'pause' : 'play'} size={21} /></button>
      <button className="reset-button" title="Volver al lanzamiento" aria-label="Volver al lanzamiento" onClick={onReset} disabled={!journey || mode === 'live'}><Icon name="rotate" size={17} /></button>
      <div className="time-slider-wrap">
        <div className="time-slider-heading"><span>{journey ? journey.name : 'Selecciona una misión'}</span><strong>{journey ? formatDuration(current) : '—'}</strong></div>
        <input type="range" min="0" max={max || 1} step={Math.max(1, max / 400)} value={current}
          onChange={e => onDate(new Date(start + Number(e.target.value) * 1000))}
          disabled={!journey || mode === 'live'} aria-label="Tiempo desde el lanzamiento"
          style={{ '--progress': `${max ? 100 * current / max : 0}%` } as CSSProperties} />
        <div className="time-slider-bottom"><span>Salida</span><span>{journey ? `Duración: ${formatDuration(max)}` : 'Sin trayectoria seleccionada'}</span></div>
      </div>
      <select className="speed-select" title="Velocidad de reproducción" aria-label="Velocidad de reproducción" disabled={!journey || mode === 'live'} value={speed} onChange={e => onSpeed(Number(e.target.value))}>
        <option value={3600}>1 h/s</option><option value={21600}>6 h/s</option><option value={86400}>24 h/s</option>
      </select>
    </div>
    <div className="playback-date"><span><Icon name="calendar" size={14} />Fecha de visualización</span>
      <input type="datetime-local" value={localInput(date)} disabled={mode === 'live'} onChange={e => { const d = new Date(e.target.value); if (!Number.isNaN(d.getTime())) onDate(d) }} />
      {mode === 'live' && <span className="playback-live-note">Hora de tu ordenador</span>}</div>
  </div>
}
