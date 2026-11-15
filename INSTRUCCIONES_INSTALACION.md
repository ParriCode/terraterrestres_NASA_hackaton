# ORBITAL4B | Proyecto completo

Este ZIP contiene el proyecto completo construido a partir de la versión unificada y del nuevo control de tiempo fijo de estancia lunar.

## Contenido
- `backend/`: FastAPI, misiones, optimizador, simulación, efemérides y pruebas.
- `frontend/`: React/TypeScript, componentes, estilos, tipos y SVG.
- `run.py`: arranque simultáneo del backend y frontend en Windows y Linux.
- `README.md`: funcionamiento, rutas y limitaciones conocidas.
- `.gitignore`: exclusiones habituales para Python y Node.

## Primer arranque
Desde la raíz de la carpeta extraída:

Windows (PowerShell):
```powershell
cd backend
python -m pip install -e ".[test]"
cd ..\frontend
npm ci
cd ..
python run.py
```

Linux:
```bash
cd backend
python3 -m pip install -e '.[test]'
cd ../frontend
npm ci
cd ..
python3 run.py
```

Frontend: http://localhost:5173/  |  API: http://127.0.0.1:8000/docs

## Pruebas
Desde `backend/`:
```bash
python -m pytest tests/test_mission_contract.py tests/test_lunar_orbit_return.py -q
```
Desde `frontend/`:
```bash
npm run build
```

## Notas
- El formulario Apolo 11 pide un tiempo de permanencia en órbita lunar (horas), además de la altitud.
- El motor respeta la duración fija solicitada. La cantidad de vueltas se calcula y se muestra tras integrar la trayectoria.
- El tiempo solicitado no garantiza una solución física válida; dependerá de las efemérides, la ventana total y la convergencia del optimizador.
- El optimizador de ida/vuelta emplea SciPy/DOP853, no debe describirse como RK2.
- La llegada a 120 km de altitud no modela un aterrizaje ni la reentrada atmosférica.
- No se incluyen `.git`, `node_modules`, cachés ni entornos virtuales. Si ya trabajas en el repositorio, conserva tu carpeta `.git` y revisa diferencias antes de reemplazar archivos.
