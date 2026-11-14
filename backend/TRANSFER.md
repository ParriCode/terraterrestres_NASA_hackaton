# Transferencia planar Tierra–Luna y optimizador Δv

Desde `backend/`, instala `pip install -e '.[test]'`.

## Optimizador de misión (`optimize_transfer`)

El flujo guiado optimiza el $\Delta v$ total estimado sujeta a una fecha de salida
y un tiempo máximo de vuelo (`max_duration_s`), partiendo de una órbita circular
prograde de aparcamiento terrestre (por defecto `parking_alt_m = 200_000` m):

```python
from datetime import datetime, timezone
from app.services.mission_optimizer import optimize_transfer

opt = optimize_transfer(
    date=datetime(2026, 11, 14, tzinfo=timezone.utc),
    max_duration_s=10 * 86400,
    parking_alt_m=200_000.0,
)

print(opt.transfer.t1_s, opt.transfer.total_delta_v_m_s)
print(opt.transfer.launch_delta_v_m_s, opt.transfer.arrival_delta_v_m_s)
```

1. **Cribado rápido (Lambert 2 cuerpos):** explora duraciones desde
   `min_duration_s = 2,5 días` hasta `max_duration_s` cada `0,5 días`, junto con
   30 ángulos de salida (cada 12°) y 6 ángulos de llegada (cada 60°) en ambos
   sentidos (`prograde=True/False`). Estima:
   $$\Delta v_{\text{est}} = \lVert \mathbf{v}_{\text{dep,rel}} - \mathbf{v}_{\text{circ,prograde}} \rVert + \sqrt{v_\infty^2 + v_{\text{escape,Luna}}^2}$$
   Los tiempos por debajo de 2,5 días devuelven `no_feasible_solution` por
   encontrarse fuera del dominio de búsqueda configurado.
2. **Deduplicación y validación DOP853:** agrupa candidatos por región
   temporal y angular, valida los mejores representantes con `F()` (propagación
   DOP853 con eventos Tierra/Luna) y realiza un refinamiento local acotado por
   `max_duration_s`.

## Modo avanzado / legacy (`design_transfer` y `F`)

```python
from datetime import datetime, timezone
from app.services.transfer_service import design_transfer

result = design_transfer(
    date=datetime(2026, 11, 14, tzinfo=timezone.utc),
    duration_s=10 * 86400,
    launch_angle_deg=90,
    arrival_angle_deg=0,
    objective="energia",  # "energia", "distancia" o "delta_v"
    mass_kg=1,
    parking_alt_m=0.0,
)

position, velocity = result.C(5 * 86400)
print(result.pos(0), result.speed(0))
print(result.launch_delta_v_m_s, result.arrival_delta_v_m_s, result.total_delta_v_m_s)
```

`design_transfer` carga el catálogo NASA y dos tablas de Horizons (Tierra y
Luna) usando interpolación cúbica de Hermite. Todas las magnitudes están en SI.

## Modelo, supuestos y límites

- **Marco planar baricéntrico:** el plano es el del movimiento relativo
  Tierra–Luna en `t0`, con origen en el baricentro Tierra–Luna (`500@3`), eje X
  en la proyección del equinoccio vernal (ICRF) y eje Y en el sentido del
  movimiento lunar. Se ignoran componentes fuera del plano, rotación terrestre y
  terceros cuerpos (incluido el Sol).
- **Órbita de aparcamiento:** `v_circ = sqrt(mu_earth / (R_earth + parking_alt_m))`
  en dirección tangencial prograde. `launch_delta_v_m_s` es la norma de la
  diferencia vectorial respecto a dicha velocidad circular.
- **Llegada a la Luna (no es aterrizaje seguro):** `arrival_delta_v_m_s` mide
  en la propagación DOP853 la velocidad relativa nave–Luna en el contacto con la
  superficie lunar, asumiendo un frenado impulsivo idealizado hasta velocidad
  cero. No modela descenso propulsado, guiado ni estabilidad de aterrizaje.
- **Validación de impactos:** `F()` permite salidas tangenciales o ligeramente
  interiores desde la órbita de aparcamiento y delega en la detección de eventos
  de `propagate_planar` el descarte de reimpactos terrestres o contactos lunares
  anticipados (`t < t1 - 60 s`).
- **Propelente opcional:** `app/services/propulsion.py` implementa la ecuación
  ideal del cohete `m_prop = m0 * (1 - exp(-Δv / (Isp * g0)))` únicamente cuando
  se proporcionan explícitamente masa inicial e `Isp`.

## API

Arranca `uvicorn app.main:app --reload`:

### `POST /transfers/optimize`

```json
{
  "date": "2026-11-14T00:00:00Z",
  "max_duration_s": 864000,
  "parking_alt_m": 200000,
  "samples": 200
}
```

Opcionalmente acepta `"initial_mass_kg"` e `"isp_s"` (ambos juntos) para añadir
la estimación idealizada de propelente.

- Respuestas `200`: `"status": "ok"` (con la transferencia seleccionada, desglose
  $\Delta v$, muestras y curva `tradeoff` de cribado Lambert) o
  `"status": "no_feasible_solution"` (con `reasons` y `tradeoff`).
- Errores: `422` si los parámetros de entrada no son válidos y `502` si falla
  NASA/JPL Horizons.

### `POST /transfers` (avanzado / legacy)

```json
{
  "date": "2026-11-14T00:00:00Z",
  "duration_s": 864000,
  "launch_angle_deg": 90,
  "arrival_angle_deg": 0,
  "objective": "energia",
  "mass_kg": 1,
  "samples": 200
}
```

Pruebas reproducibles sin red:
`python -m pytest tests/test_propulsion.py tests/test_transfer.py tests/test_mission_optimizer.py tests/test_transfer_api.py`.

Referencia de parámetros Horizons: https://ssd-api.jpl.nasa.gov/doc/horizons.html