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
    <p className="result-caption">{transfer.mission_mode === 'lunar_orbit_return' ? 'Apolo 11 · ' : transfer.mission_mode === 'free_return' ? 'Apolo 8/13 · ' : ''}{transfer.mission_solution || transfer.mission_one_way_delta_v_m_s != null ? 'Optimización orbital (Δv)' : transfer.objective === 'energia' ? 'Mínima energía' : 'Mínima distancia'} · {transfer.source}</p>
    <div className="result-grid">
      <div><span>Velocidad inicial (baricéntrica)</span><strong>{formatKmS(norm(v0))}</strong>
        <small>({kms(v0[0])}, {kms(v0[1])}) km/s</small></div>
      <div><span>Velocidad respecto a la Tierra</span><strong>{formatKmS(transfer.launch_speed_m_s)}</strong></div>
      <div><span>{transfer.mission_solution ? 'Energía cinética inicial (respecto a Tierra)' : 'Energía de lanzamiento'}</span><strong>{formatMJ(transfer.launch_energy_j)}</strong>
        <small>{transfer.mass_kg} kg, respecto a la Tierra</small></div>
      <div><span>Longitud del recorrido{transfer.path_length_approximate ? ' (aprox.)' : ''}</span><strong>{formatKm(transfer.path_length_m)}</strong></div>
      <div><span>{transfer.earth_entry ? 'Desviación del corredor terrestre' : 'Error de llegada'}</span><strong>{formatMeters(transfer.arrival_error_m)}</strong></div>
      {transfer.arrival_angle_deg !== null && <div><span>Ángulo de llegada seleccionado</span><strong>{transfer.arrival_angle_deg.toLocaleString('es-ES', { maximumFractionDigits: 2 })}°</strong>
        <small>Mejor candidato evaluado, sin garantía de óptimo global</small>
        {transfer.optimization && <small>
          {transfer.optimization.attempted_angles_deg.length} ángulos intentados · {transfer.optimization.valid_candidates} candidatos válidos
          {transfer.optimization.search_complete ? ' · Búsqueda acotada finalizada' : ' · Búsqueda limitada por tiempo'}
        </small>}</div>}
    </div>
    {transfer.lunar_orbit && !transfer.mission_solution && <>
      <h3><Icon name="orbit" size={14} />Órbita lunar y retorno</h3>
      <div className="result-grid">
        <div><span>Tiempo de regreso</span><strong>{(transfer.duration_s / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días</strong>
          <small>Máximo solicitado: {((transfer.requested_duration_s ?? transfer.duration_s) / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días</small></div>
        <div><span>Altitud orbital</span><strong>{transfer.lunar_orbit.altitude_km} km</strong>
          <small>{transfer.lunar_orbit.actual_revolutions.toFixed(2)} vueltas propagadas</small></div>
        <div><span>{transfer.earth_entry?.validated ? 'Llegada a la Tierra' : 'Radio de regreso declarado'}</span>
          <strong>{transfer.earth_entry?.validated
            ? `${transfer.earth_entry.altitude_km} km de altitud`
            : transfer.return_interface_radius_m != null ? formatKm(transfer.return_interface_radius_m) : 'No disponible'}</strong>
          <small>{transfer.earth_entry?.validated ? 'Entrada atmosférica aproximada, sin aterrizaje simulado' : 'Radio desde el centro de la Tierra, no implica entrada atmosférica'}</small></div>
        {transfer.earth_entry && <div><span>Velocidad relativa al entrar</span><strong>{formatKmS(transfer.earth_entry.relative_speed_m_s)}</strong>
          <small>Sin evaluación térmica ni aerodinámica</small></div>}
        <div><span>Δv de inserción y salida</span><strong>{formatKmS(transfer.total_maneuver_delta_v_m_s ?? 0)}</strong>
          <small>No incluye el lanzamiento ni demuestra combustible suficiente</small></div>
      </div>
      <p className="results-disclaimer">Se han propagado tres arcos y dos impulsos ideales. La búsqueda es acotada. No se simula reentrada ni aterrizaje.</p>
    </>}
    {transfer.lunar_orbit && !transfer.mission_solution && <p className="form-note">Fase: <strong>{state.t_s < transfer.lunar_orbit.orbit_insertion_t_s ? 'Viaje hacia la Luna'
      : state.t_s < transfer.lunar_orbit.orbit_departure_t_s ? 'En órbita lunar'
        : state.t_s >= transfer.duration_s - 1e-6 ? 'Llegada a la Tierra (120 km)' : 'Regreso hacia la Tierra'}</strong></p>}
    {transfer.mission_one_way_delta_v_m_s != null && <div className="result-grid"><div><span>Δv total de transferencia (ORBITAL4B)</span><strong>{formatKmS(transfer.mission_one_way_delta_v_m_s)}</strong><small>Duración elegida por el optimizador, no necesariamente la máxima.</small></div></div>}
    {transfer.mission_solution && <>
      <h3><Icon name="orbit" size={14} />Misión 3D calculada</h3>
      <div className="result-grid">
        <div><span>Duración real / máxima</span><strong>{(transfer.duration_s / 86400).toFixed(2)} / {((transfer.requested_duration_s ?? transfer.duration_s) / 86400).toFixed(2)} días</strong></div>
        <div><span>Δv total de maniobras</span><strong>{formatKmS(transfer.mission_solution.total_delta_v_m_s)}</strong>
          <small>TLI {formatKmS(transfer.mission_solution.tli_delta_v_m_s)} · LOI {formatKmS(transfer.mission_solution.loi_delta_v_m_s)} · TEI {formatKmS(transfer.mission_solution.tei_delta_v_m_s)}</small></div>
        <div><span>Altitud mínima lunar</span><strong>{transfer.mission_solution.min_lunar_altitude_km.toFixed(1)} km</strong></div>
        {transfer.mission_solution.mode === 'lunar_orbit' && <div><span>Vueltas lunares verificadas</span><strong>{transfer.mission_solution.actual_lunar_revolutions.toFixed(2)}</strong></div>}
        <div><span>Llegada a la Tierra</span><strong>{transfer.earth_entry?.altitude_km.toFixed(2)} km de altitud</strong><small>Movimiento entrante: {transfer.earth_entry?.inbound ? 'sí' : 'no'}</small></div>
        <div><span>Velocidad relativa de llegada</span><strong>{formatKmS(transfer.earth_entry?.relative_speed_m_s ?? 0)}</strong></div>
      </div>
      <p className="results-disclaimer">Propagación de misión ORBITAL4B: SciPy solve_ivp. Llegada validada al corredor terrestre, no reentrada aerodinámica ni aterrizaje. Δv de maniobras, no combustible consumido; búsqueda acotada.</p>
    </>}
    <h3><Icon name="clock" size={14} />Instante seleccionado</h3>
    <div className="result-grid">
      <div><span>Posición (x, y)</span><strong>({km(state.position_m[0])}, {km(state.position_m[1])}) km</strong></div>
      <div><span>Velocidad (vx, vy)</span><strong>({kms(state.velocity_m_s[0])}, {kms(state.velocity_m_s[1])}) km/s</strong>
        <small>|v| = {formatKmS(norm(state.velocity_m_s))}</small></div>
    </div>
    <p className="results-disclaimer">{transfer.mission_solution ? 'Motor orbital 3D, proyectado al plano ICRF XY.' : 'Modelo planar baricéntrico Tierra–Luna.'} Valores intermedios interpolados localmente entre {transfer.samples.length} muestras del backend.</p>
  </aside>
}
