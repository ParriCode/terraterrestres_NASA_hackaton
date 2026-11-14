Integra el frontend React con el cálculo real de transferencias Tierra–Luna del backend. Implementa los cambios reutilizando la arquitectura existente y conservando el trabajo de José. No hagas commits ni añadas este archivo a Git.

Lee `backend/TRANSFER.md`, `services/transfer_service.py`, `controllers/transfer_controller.py` y los componentes del frontend.

El backend ya tiene `F`: Lambert → shooting → validación. `design_transfer(...)` devuelve un objeto consultable por tiempo con posición, velocidad y magnitudes de la transferencia. Usa efemérides reales de NASA proyectadas en 2D; no reimplementes la física en React.

Conecta la interfaz a `POST /transfers`:

```json
{
  "date": "2026-11-14T00:00:00Z",
  "duration_s": 864000,
  "launch_angle_deg": 90,
  "arrival_angle_deg": 0,
  "objective": "energia",
  "mass_kg": 1,
  "samples": 400
}
```

Consulta el controlador para la respuesta y crea tipos TypeScript propios: no es el contrato antiguo de `/simulations`.

Simplifica la interfaz para mostrar solo:

- Formulario: fecha, duración en días, ángulos de salida y llegada, objetivo `energia` o `distancia`. Masa fija de 1 kg.
- Botón de cálculo, estado de carga y errores claros.
- Vista 2D con Tierra, Luna, trayectoria y esfera usando las muestras del backend.
- Play/pausa, reinicio y deslizador temporal, interpolando localmente sin nuevas peticiones durante la animación.
- Resumen: velocidad inicial, energía de lanzamiento, longitud y error de llegada. Posición y velocidad del instante seleccionado.

Quita demos, mocks, sistema solar completo, reloj en vivo, instrumentos científicos, retorno libre, flybys, objetivos ficticios y gestión de múltiples misiones. Conserva solo la última transferencia y elimina código y estilos sin uso.

Respeta el marco planar baricéntrico, usa SI en la API y unidades legibles en pantalla. Gestiona fechas, CORS y errores 422/502 sin sustituir fallos por demos. Si faltan radios para dibujar, obténlos del catálogo del backend, sin duplicar constantes en React.

Comprueba el build y las pruebas relevantes. Debe funcionar el recorrido completo: formulario → cálculo real → trayectoria → consulta de posición y velocidad por tiempo.
