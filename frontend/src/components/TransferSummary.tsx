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
    <p className="result-caption">{transfer.mission_mode === 'lunar_orbit_return' ? 'Órbita lunar y regreso · ' : ''}{transfer.objective === 'energia' ? 'Mínima energía' : 'Mínima distancia'} · {transfer.source}</p>
    <div className="result-grid">
      <div><span>Velocidad inicial (baricéntrica)</span><strong>{formatKmS(norm(v0))}</strong>
        <small>({kms(v0[0])}, {kms(v0[1])}) km/s</small></div>
      <div><span>Velocidad respecto a la Tierra</span><strong>{formatKmS(transfer.launch_speed_m_s)}</strong></div>
      <div><span>Energía de lanzamiento</span><strong>{formatMJ(transfer.launch_energy_j)}</strong>
        <small>{transfer.mass_kg} kg, respecto a la Tierra</small></div>
      <div><span>Longitud del recorrido</span><strong>{formatKm(transfer.path_length_m)}</strong></div>
      <div><span>{transfer.lunar_orbit ? 'Error de llegada a esfera terrestre' : 'Error de llegada'}</span><strong>{formatMeters(transfer.arrival_error_m)}</strong></div>
      <div><span>{transfer.lunar_orbit ? 'Ángulo de llegada a la Luna' : 'Ángulo de llegada seleccionado'}</span><strong>{transfer.arrival_angle_deg.toLocaleString('es-ES', { maximumFractionDigits: 2 })}°</strong>
        <small>Mejor candidato evaluado, sin garantía de óptimo global</small>
        {transfer.optimization && <small>
          {transfer.optimization.attempted_angles_deg.length} ángulos intentados · {transfer.optimization.valid_candidates} candidatos válidos
          {transfer.optimization.search_complete ? ' · Búsqueda acotada finalizada' : ' · Búsqueda limitada por tiempo'}
        </small>}</div>
    </div>
    {transfer.lunar_orbit && <>
      <h3><Icon name="orbit" size={14} />Órbita lunar y retorno</h3>
      <div className="result-grid">
        <div><span>Tiempo de regreso</span><strong>{(transfer.duration_s / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días</strong>
          <small>Máximo solicitado: {((transfer.requested_duration_s ?? transfer.duration_s) / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días</small></div>
        <div><span>Altitud orbital</span><strong>{transfer.lunar_orbit.altitude_km} km</strong>
          <small>{transfer.lunar_orbit.actual_revolutions.toFixed(2)} vueltas propagadas</small></div>
        <div><span>Regreso al entorno terrestre</span><strong>{formatKm(transfer.return_interface_radius_m ?? 100000000)}</strong>
          <small>Radio geocéntrico, no aterrizaje</small></div>
        <div><span>Δv de inserción y salida</span><strong>{formatKmS(transfer.total_maneuver_delta_v_m_s ?? 0)}</strong>
          <small>No incluye el lanzamiento ni demuestra combustible suficiente</small></div>
      </div>
      <p className="results-disclaimer">Se han propagado tres arcos y dos impulsos ideales. La búsqueda es acotada. No se simula reentrada ni aterrizaje.</p>
    </>}
    {transfer.lunar_orbit && <p className="form-note">Fase: <strong>{state.t_s < transfer.lunar_orbit.orbit_insertion_t_s ? 'Viaje hacia la Luna'
      : state.t_s < transfer.lunar_orbit.orbit_departure_t_s ? 'En órbita lunar'
        : 'Regreso al entorno terrestre'}</strong></p>}
    <h3><Icon name="clock" size={14} />Instante seleccionado</h3>
    <div className="result-grid">
      <div><span>Posición (x, y)</span><strong>({km(state.position_m[0])}, {km(state.position_m[1])}) km</strong></div>
      <div><span>Velocidad (vx, vy)</span><strong>({kms(state.velocity_m_s[0])}, {kms(state.velocity_m_s[1])}) km/s</strong>
        <small>|v| = {formatKmS(norm(state.velocity_m_s))}</small></div>
    </div>
    <p className="results-disclaimer">Marco planar baricéntrico Tierra–Luna (eje X inicial Tierra→Luna, ejes fijos en ICRF). Valores intermedios interpolados localmente entre {transfer.samples.length} muestras del backend.</p>
  </aside>
}
