import type { TransferResponse, TransferState } from '../types/transfer'
import { formatKm, formatKmS, formatMeters, formatMJ, norm } from '../utils/transfer'
import Icon from './Icon'

type Props = { transfer: TransferResponse; state: TransferState }
const km = (m: number) => (m / 1000).toLocaleString('es-ES', { maximumFractionDigits: 0 })
const kms = (v: number) => (v / 1000).toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 3 })

export default function TransferSummary({ transfer, state }: Props) {
  const v0 = transfer.initial_velocity_m_s
  return <aside className="results-panel">
    <h2><Icon name="layers" size={16} />Resultado</h2>
    <p className="result-caption">{transfer.objective === 'energia' ? 'Mínima energía' : 'Mínima distancia'} · {transfer.source}</p>
    <div className="result-grid">
      <div><span>Velocidad inicial (baricéntrica)</span><strong>{formatKmS(norm(v0))}</strong>
        <small>({kms(v0[0])}, {kms(v0[1])}) km/s</small></div>
      <div><span>Velocidad respecto a la Tierra</span><strong>{formatKmS(transfer.launch_speed_m_s)}</strong></div>
      <div><span>Energía de lanzamiento</span><strong>{formatMJ(transfer.launch_energy_j)}</strong>
        <small>{transfer.mass_kg} kg, respecto a la Tierra</small></div>
      <div><span>Longitud del recorrido</span><strong>{formatKm(transfer.path_length_m)}</strong></div>
      <div><span>Error de llegada</span><strong>{formatMeters(transfer.arrival_error_m)}</strong></div>
    </div>
    <h3><Icon name="clock" size={14} />Instante seleccionado</h3>
    <div className="result-grid">
      <div><span>Posición (x, y)</span><strong>({km(state.position_m[0])}, {km(state.position_m[1])}) km</strong></div>
      <div><span>Velocidad (vx, vy)</span><strong>({kms(state.velocity_m_s[0])}, {kms(state.velocity_m_s[1])}) km/s</strong>
        <small>|v| = {formatKmS(norm(state.velocity_m_s))}</small></div>
    </div>
    <p className="results-disclaimer">Marco planar baricéntrico Tierra–Luna (eje X inicial Tierra→Luna, ejes fijos en ICRF). Valores intermedios interpolados localmente entre {transfer.samples.length} muestras del backend.</p>
  </aside>
}
