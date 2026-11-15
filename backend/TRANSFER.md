# Transferencia planar Tierra–Luna

Desde `backend/`, instala `pip install -e '.[test]'`.

```python
from datetime import datetime, timezone
from app.services.transfer_service import design_transfer

result = design_transfer(
    date=datetime(2026, 11, 14, tzinfo=timezone.utc),
    duration_s=10 * 86400,
    launch_angle_deg=90,
    arrival_angle_deg=0,
    objective="energia",  # o "distancia"
    mass_kg=1,
)

position, velocity = result.C(5 * 86400)
print(result.pos(0), result.speed(0))
print(result.initial_velocity_m_s)
print(result.launch_speed_m_s, result.launch_energy_j)
print(result.path_length_m, result.arrival_error_m)
print(result.energy(5 * 86400))
```

`design_transfer` carga el catálogo NASA y dos tablas de Horizons (Tierra y
Luna). Usa interpolación cúbica de Hermite con posiciones y velocidades, con
muestras horarias por defecto. Una consulta a `C(t)` no realiza peticiones ni
reintegra la trayectoria. Los tiempos se miden desde la fecha inicial y deben
estar dentro del intervalo de vuelo; las magnitudes están en SI.

Para especificar directamente los extremos, crea `PlanarScenario(date,
duration_s)` y llama a `F(x0, x1, t0, t1, "energia", scenario=scenario)`.
Ambos extremos son tuplas `(x, y, 0)` en las superficies de los cuerpos.

## Modelo y búsqueda

El eje X inicial apunta de Tierra a Luna. El eje Y completa el plano del
movimiento relativo inicial, calculado con posición y velocidad de Horizons.
Los ejes permanecen fijos respecto a ICRF, y el origen es el baricentro
Tierra–Luna (`500@3`). Se proyecta el movimiento real sobre ese plano; se
ignoran las componentes fuera del plano, la rotación y la gravedad de otros
cuerpos. Es una aproximación planar con efemérides reales, no una reproducción
completa de la dinámica del sistema solar. `scenario.basis_icrf` permite
identificar los ejes usados.

F usa Lambert terrestre como semilla y shooting de dos incógnitas para resolver
`R(v0) = r(t1; v0) - x1 = 0`. La propagación DOP853 reutiliza la gravedad del
proyecto, con salida densa, rtol=1e-10 y atol=1e-6. RK2 continúa disponible para
el flujo de simulaciones existente. Durante la búsqueda se permite prolongar
matemáticamente una trayectoria dentro de los cuerpos; la validación posterior
descarta impactos terrestres, contactos lunares anteriores a t1−60 s, salida
hacia dentro y llegada desde dentro. Tolerancia de llegada: 1000 m.

Prueba ambos sentidos y, si fallan, semillas con tiempos Lambert ±2 %. Selecciona
la mejor candidata válida encontrada, sin garantizar un óptimo global.
Si ninguna es válida lanza `TransferNotFoundError`; cambia ángulos o duración.

`launch_energy_j = 0.5 * mass_kg * launch_speed_m_s**2` mide el impulso respecto
al centro terrestre (sin rotación). `energy(t)` devuelve energía cinética,
potencial y mecánica en el marco baricéntrico; no se presupone conservación
porque los cuerpos se mueven con efemérides prescritas. `path_length_m` se
aproxima con 4000 muestras respecto al centro terrestre en ejes fijos.

## API

Arranca `uvicorn app.main:app --reload` y usa `POST /transfers`:

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

Este endpoint siempre calcula con NASA, independientemente del modo mock de
`/simulations`. Devuelve las magnitudes y muestras para visualización; una
función Python no se serializa en JSON. Errores: 502 si falla Horizons y 422 si
no se encuentra una transferencia válida. El cálculo es síncrono y puede tardar
si necesita varias semillas; cada petición puede lanzar múltiples integraciones.

Pruebas reproducibles sin red:
`python -m pytest tests/test_transfer.py tests/test_lambert.py tests/test_shooting.py`.
Las pruebas usan efemérides circulares controladas, no las sustituyen en producción.

Referencia de parámetros: https://ssd-api.jpl.nasa.gov/doc/horizons.html
