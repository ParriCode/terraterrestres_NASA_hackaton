import { SCIENCE_CATALOG_VERSION, SCIENCE_GOALS, SCIENCE_INSTRUMENTS, calculateScienceBudget } from '../science/catalog'
import type { ScienceDesign, ScienceGoalId, ScienceInstrumentId } from '../science/catalog'
import Icon from './Icon'

type Props = {
  design: ScienceDesign
  duration_s: number
  onChange: (design: ScienceDesign) => void
}

const fmt = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 })

export default function SciencePayloadSelector({ design, duration_s, onChange }: Props) {
  const budget = calculateScienceBudget(design, duration_s)
  const selectedGoal = SCIENCE_GOALS.find(goal => goal.id === design.goal_id)!

  function selectGoal(goal_id: ScienceGoalId) {
    const goal = SCIENCE_GOALS.find(g => g.id === goal_id)!
    // Al cambiar el objetivo, se recomienda su instrumento sin descartar los demás
    const instrument_ids = design.instrument_ids.includes(goal.requiredInstrument)
      ? [...design.instrument_ids]
      : [...design.instrument_ids, goal.requiredInstrument]
    onChange({ ...design, goal_id, instrument_ids })
  }

  function toggleInstrument(id: ScienceInstrumentId) {
    onChange({
      ...design,
      instrument_ids: design.instrument_ids.includes(id)
        ? design.instrument_ids.filter(x => x !== id)
        : [...design.instrument_ids, id],
    })
  }

  return <section className="science-selector" aria-label="Objetivo y carga científica">
    <div className="science-section-heading">
      <div>
        <div className="eyebrow"><Icon name="target" size={13} /> T11 · OBJETIVO CIENTÍFICO</div>
        <h3>¿Qué quieres investigar?</h3>
      </div>
      <span className="science-provisional-chip">CATÁLOGO DE PRUEBA</span>
    </div>
    <div className="science-goal-list" role="radiogroup" aria-label="Seleccionar objetivo científico">
      {SCIENCE_GOALS.map(goal => <label className={`science-goal-choice ${design.goal_id === goal.id ? 'active' : ''}`} key={goal.id}>
        <input type="radio" name="science-goal" checked={design.goal_id === goal.id} onChange={() => selectGoal(goal.id)} />
        <span><strong>{goal.name}</strong><small>{goal.description}</small></span>
      </label>)}
    </div>
    <div className="science-section-heading payload-heading">
      <div className="eyebrow"><Icon name="layers" size={13} /> CARGA ÚTIL</div>
      <span className="science-subtle">Selecciona instrumentos</span>
    </div>
    <div className="science-instrument-list">
      {SCIENCE_INSTRUMENTS.map(inst => {
        const checked = design.instrument_ids.includes(inst.id)
        const needed = selectedGoal.requiredInstrument === inst.id
        return <label key={inst.id} className={`science-instrument ${checked ? 'active' : ''}`}>
          <input type="checkbox" checked={checked} onChange={() => toggleInstrument(inst.id)} />
          <span className="science-instrument-main"><strong>{inst.name} {needed && <em>Objetivo</em>}</strong><small>{inst.description}</small>
            <span className="science-instrument-metrics">{fmt.format(inst.mass_kg)} kg · {fmt.format(inst.power_w)} W · {fmt.format(inst.data_mb_day)} MB/día</span>
          </span>
        </label>
      })}
    </div>
    {!budget.goal_has_required_instrument && <div className="science-target-warning" role="alert"><Icon name="alert" size={14} />
      El objetivo requiere «{SCIENCE_INSTRUMENTS.find(i => i.id === selectedGoal.requiredInstrument)?.name}». Selecciónalo para continuar.
    </div>}
    <div className="science-budget" aria-live="polite">
      <div className="science-budget-title">Impacto de la carga útil <span>Respecto a llevar 0 instrumentos</span></div>
      <div className="science-budget-grid">
        <div><small>Masa añadida</small><strong>+{fmt.format(budget.mass_kg)} <span>kg</span></strong></div>
        <div><small>Potencia requerida</small><strong>+{fmt.format(budget.power_w)} <span>W</span></strong></div>
        <div><small>Datos generados</small><strong>+{fmt.format(budget.data_mb_day)} <span>MB/día</span></strong></div>
      </div>
      <div className="science-projection">Proyección para {fmt.format(duration_s / 86400)} días: <strong>{fmt.format(budget.projected_data_mb)} MB</strong> si todos los instrumentos permanecieran activos.</div>
    </div>
    <p className="science-legal"><Icon name="info" size={13} />
      Las masas, potencias y tasas de datos son <strong>hipótesis sintéticas</strong> ({SCIENCE_CATALOG_VERSION}). No incluyen batería, energía total, almacenamiento ni capacidad de transmitir datos. Pendiente de validación por P3. Este diseño aún no altera el cálculo RK2 del backend v1.
    </p>
  </section>
}
