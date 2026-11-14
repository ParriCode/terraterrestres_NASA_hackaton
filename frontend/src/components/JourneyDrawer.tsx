import type { CSSProperties } from 'react'
import type { Journey } from '../types/simulation'
import { elapsedAt, formatDuration, journeyProgress, shortDate } from '../utils/trajectory'
import Icon from './Icon'
import { calculateScienceBudget, scienceGoalName } from '../science/catalog'

type Props = {
  open: boolean; journeys: Journey[]; selectedId: string | null; date: Date;
  onClose: () => void; onNew: () => void; onSelect: (id: string) => void;
  onToggle: (id: string) => void; onDelete: (id: string) => void;
}
export default function JourneyDrawer({ open, journeys, selectedId, date, onClose, onNew, onSelect, onToggle, onDelete }: Props) {
  return <aside className={`journey-drawer ${open ? 'is-open' : ''}`} aria-hidden={!open} aria-label="Mis viajes">
    <div className="drawer-heading">
      <div><div className="eyebrow">CENTRO DE MISIONES</div><h2>Mis viajes <span className="count-chip">{journeys.length}</span></h2></div>
      <button className="icon-button" onClick={onClose} aria-label="Cerrar viajes" title="Cerrar"><Icon name="x" /></button>
    </div>
    <div className="drawer-body">
      {journeys.length === 0 ? <div className="empty-trips">
        <div className="empty-icon"><Icon name="orbit" size={34} /></div>
        <h3>Todavía no hay misiones</h3>
        <p>Crea tu primer viaje para empezar a explorar su trayectoria y el tiempo transcurrido.</p>
      </div> : <div className="journey-list">
        {journeys.map((j, idx) => {
          const selected = j.id === selectedId
          const progress = journeyProgress(j, date)
          const dateStart = new Date(j.launch_iso).getTime()
          const before = date.getTime() < dateStart
          const after = progress >= 1
          return <div key={j.id} className={`journey-card ${selected ? 'active' : ''}`} style={{ '--journey-color': j.color } as CSSProperties}>
            <button className="journey-card-main" onClick={() => onSelect(j.id)}>
              <div className="journey-card-top"><span className="journey-counter">{String(idx + 1).padStart(2, '0')}</span>
                <span className="journey-card-title">{j.name}</span>
                <span className={`source-chip ${j.source === 'demo' ? 'demo' : ''}`}>{j.source === 'demo' ? 'DEMO' : 'PYTHON'}</span></div>
              <div className="journey-route"><span>Tierra</span><Icon name="arrow-right" size={13} /><span>Luna</span>{j.route_kind === 'lunar_free_return' && <><Icon name="arrow-right" size={13} /><span>Tierra</span></>}</div>
              {j.route_kind === 'lunar_free_return' && <div className="journey-subtype">Retorno libre lunar · {j.source === 'demo' ? 'demostración visual' : 'datos de Python'}</div>}
              {j.science && <div className="journey-science-tag"><Icon name="target" size={12} />{scienceGoalName(j.science.goal_id)} · +{calculateScienceBudget(j.science, j.result.config.duration_s).mass_kg} kg de carga</div>}
              <div className="journey-track"><span style={{ width: `${progress * 100}%` }} /></div>
              <div className="journey-card-meta"><span><Icon name="clock" size={13} />{before ? 'Pendiente' : after ? 'Finalizado' : formatDuration(elapsedAt(j, date))}</span>
                <span>{Math.round(progress * 100)} %</span></div>
            </button>
            <div className="journey-card-actions">
              <span className="launch-label">Salida: {shortDate(j.launch_iso)}</span>
              <div className="action-buttons">
                <button onClick={() => onToggle(j.id)} title={j.visible ? 'Ocultar trayectoria' : 'Mostrar trayectoria'} aria-label={j.visible ? `Ocultar ${j.name}` : `Mostrar ${j.name}`}><Icon name={j.visible ? 'eye' : 'eye-off'} size={17} /></button>
                <button onClick={() => onDelete(j.id)} title="Eliminar viaje" aria-label={`Eliminar ${j.name}`}><Icon name="trash" size={16} /></button>
              </div>
            </div>
          </div>
        })}
      </div>}
    </div>
    <div className="drawer-footer"><button className="primary-button wide" onClick={onNew}><Icon name="plus" size={17} />Crear nuevo viaje</button>
      <p>Los viajes de demostración no son cálculos de navegación.</p></div>
  </aside>
}
