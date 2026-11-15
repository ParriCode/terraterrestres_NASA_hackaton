# ORBITAL4B

Simulador de transferencias Tierra-Luna, retorno libre y órbita lunar con regreso, con backend FastAPI y frontend React/TypeScript.

## Arranque

Desde la raíz del proyecto:

```sh
python run.py
```

En Linux puede ser necesario usar `python3 run.py`. Antes de arrancar, instala las dependencias del backend en un entorno virtual (`python -m pip install -e "./backend[test]"`) y las del frontend con `cd frontend && npm ci`.

- Frontend: http://localhost:5173/
- API: http://127.0.0.1:8000/docs
- Transferencia clásica: `POST /transfers`
- Optimización clásica: `POST /transfers/optimize`
- Trayectorias de misión: `POST /missions/optimize` y `POST /missions/round-trip`

## Organización científica

- `backend/app/services/mission_optimizer.py`: optimización de misiones.
- `backend/app/controllers/mission_controller.py`: API de misiones.
- `backend/app/mission/`: componentes especializados de datos, gravedad, Lambert, propagación y servicios auxiliares de misión. Separados de las implementaciones existentes con distinta interfaz para evitar colisiones de nombres y cambios de comportamiento.
- `backend/app/services/transfer_service.py`: servicio de transferencia existente.
- `frontend/src/api/missions.ts`: adaptador de resultados científicos a la visualización.

## Configuración de órbita lunar

En la modalidad **Apolo 11**, el usuario indica la **altitud lunar** y el **tiempo fijo de permanencia en órbita**, en horas. React convierte las horas a segundos (`lunar_stay_s`) para el endpoint `POST /missions/round-trip`. El motor propaga la nave hasta el instante de salida solicitado; no añade otra revolución ni convierte un número de vueltas en duración.

Las **vueltas lunares efectivamente propagadas** se muestran únicamente como resultado de la simulación: dependen de la altitud y de la dinámica integrada. La duración máxima de misión debe cubrir ida, estancia y retorno. Si no encuentra una solución válida con ese tiempo, responde `no_feasible_solution`.

**Nota sobre compatibilidad:** el endpoint antiguo `/transfers/lunar-orbit-return` pertenece a un simulador planar distinto y mantiene su interfaz histórica. La interfaz React actual utiliza `/missions/round-trip`, que acepta directamente `lunar_stay_s`.

## Limitaciones

La optimización de ida y vuelta utiliza `solve_ivp`/DOP853. No debe confundirse con la implementación RK2 de otras partes del proyecto. La llegada al corredor terrestre de 120 km no constituye un aterrizaje ni una simulación de reentrada atmosférica. Las búsquedas están acotadas y no garantizan óptimo global.

## Equipo

Contribuciones de un equipo de cinco integrantes. El historial Git conserva la autoría de los cambios; los identificadores de código, los mensajes y las rutas HTTP son neutros y describen la función de cada módulo.
