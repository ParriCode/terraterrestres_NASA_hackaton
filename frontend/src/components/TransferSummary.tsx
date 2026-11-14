import type { OptimizeTransferOkResponse, TransferState } from '../types/transfer'
import { formatKm, formatKmS, formatMeters, norm } from '../utils/transfer'
import Icon from './Icon'

type Props = { transfer: OptimizeTransferOkResponse; state: TransferState }
const km = (m: number) => (m / 1000).toLocaleString('es-ES', { maximumFractionDigits: 0 })
const kms = (v: number) => (v / 1000).toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
const days = (s: number) => (s / 86400).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const kg = (m: number) => m.toLocaleString('es-ES', { maximumFractionDigits: 1 })

export default function TransferSummary({ transfer, state }: Props) {
  const v0 = transfer.initial_velocity_m_s
  return <aside className="results-panel">
    <h2><Icon name="layers" size={16} />Transferencia seleccionada</h2>
    <p className="result-caption">Mínimo Δv validado (DOP853) · {transfer.source}</p>
    <div className="result-grid">
      <div><span>Duración elegida</span><strong>{days(transfer.duration_s)} días</strong>
        <small>Límite máximo: {days(transfer.max_duration_s)} días</small></div>
      <div><span>Δv total estimado</span><strong>{formatKmS(transfer.total_delta_v_m_s)}</strong>
        <small>Salida desde {(transfer.parking_alt_m / 1000).toFixed(0)} km + frenado lunar</small></div>
      <div><span>Δv de salida</span><strong>{formatKmS(transfer.launch_delta_v_m_s)}</strong>
        <small>Diferencia vectorial respecto a órbita circular prograde</small></div>
      <div><span>Δv de llegada (frenado impulsivo idealizado)</span><strong>{formatKmS(transfer.arrival_delta_v_m_s)}</strong>
        <small>v∞ ≈ {formatKmS(transfer.arrival_v_infinity_m_s)} · Hasta v = 0 en superficie (no es aterrizaje seguro)</small></div>
      <div><span>Distancia recorrida</span><strong>{formatKm(transfer.path_length_m)}</strong></div>
      <div><span>Error de llegada</span><strong>{formatMeters(transfer.arrival_error_m)}</strong></div>
      {transfer.propellant && <div>
        <span>Propelente estimado (idealizado)</span>
        <strong>{kg(transfer.propellant.propellant_mass_kg)} kg</strong>
        <small>m₀ = {kg(transfer.propellant.initial_mass_kg)} kg · Isp = {transfer.propellant.isp_s} s</small>
      </div>}
    </div>
    <h3><Icon name="clock" size={14} />Instante seleccionado</h3>
    <div className="result-grid">
      <div><span>Posición (x, y)</span><strong>({km(state.position_m[0])}, {km(state.position_m[1])}) km</strong></div>
      <div><span>Velocidad (vx, vy)</span><strong>({kms(state.velocity_m_s[0])}, {kms(state.velocity_m_s[1])}) km/s</strong>
        <small>|v| = {formatKmS(norm(state.velocity_m_s))} · v₀ baricéntrica = {formatKmS(norm(v0))}</small></div>
    </div>
    <p className="results-disclaimer">Modelo planar baricéntrico Tierra–Luna. El Δv de llegada representa un frenado impulsivo idealizado en superficie sin perfil de descenso propulsado ni guiado de aterrizaje. Muestras interpoladas entre {transfer.samples.length} puntos del backend.</p>
  </aside>
}
