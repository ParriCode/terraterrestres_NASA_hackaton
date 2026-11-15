/** 1 unidad de escena = 10 000 km. El centro de cada cuerpo nunca cambia. */
export function capBodyRadius(physicalRadius: number, multiplier: number, nearestShipCenter: number): number {
  // No agrandar un cuerpo hasta engullir una trayectoria que físicamente lo evita.
  // El margen de 0.001 unidades (~10 km) deja una separación visual mínima.
  if (!Number.isFinite(nearestShipCenter)) return physicalRadius * multiplier
  return Math.max(physicalRadius, Math.min(physicalRadius * multiplier, nearestShipCenter - 0.001))
}

/** El modelo del cohete mide como máximo ~0.92 radios de escala desde su centro. */
export function shipScaleForClearance(clearance: number, desiredScale: number): number {
  if (clearance <= 0) return 0
  // Reservar el 20% de la distancia al borde (si existe); reducir junto al cuerpo.
  return Math.min(desiredScale, Math.max(0, clearance * 0.8 / 0.95))
}
