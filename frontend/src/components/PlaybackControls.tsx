import type { CSSProperties } from 'react'
import { formatDuration, formatUtc } from '../utils/transfer'
import Icon from './Icon'

type Props = {
  start: Date; duration: number; time: number; playing: boolean; speed: number
  onToggle: () => void; onReset: () => void; onTime: (t: number) => void; onSpeed: (v: number) => void
}

export default function PlaybackControls({ start, duration, time, playing, speed, onToggle, onReset, onTime, onSpeed }: Props) {
  return <div className="playback-shell">
    <button className="play-main-button" onClick={onToggle} aria-label={playing ? 'Pausar' : 'Reproducir'} title={playing ? 'Pausar' : 'Reproducir'}>
      <Icon name={playing ? 'pause' : 'play'} size={20} /></button>
    <button className="reset-button" onClick={onReset} aria-label="Reiniciar" title="Volver a la salida"><Icon name="rotate" size={16} /></button>
    <div className="time-slider-wrap">
      <div className="time-slider-heading"><span>{formatUtc(new Date(start.getTime() + time * 1000))}</span><strong>T+ {formatDuration(time)}</strong></div>
      <input type="range" min={0} max={duration} step={duration / 2000} value={time}
        onChange={e => onTime(Number(e.target.value))} aria-label="Tiempo desde la salida"
        style={{ '--progress': `${100 * time / duration}%` } as CSSProperties} />
      <div className="time-slider-bottom"><span>Salida</span><span>Llegada · {formatDuration(duration)}</span></div>
    </div>
    <select className="speed-select" value={speed} onChange={e => onSpeed(Number(e.target.value))} aria-label="Velocidad de reproducción">
      <option value={3600}>1 h/s</option><option value={21600}>6 h/s</option><option value={86400}>1 d/s</option>
    </select>
  </div>
}
