# ORBITAL4B | Proyecto completo

Este ZIP contiene el proyecto completo construido a partir de la versión unificada y del último cambio del formulario de vueltas lunares.

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
- El formulario Apolo 11 admite seleccionar un entero de 1 a 100 vueltas.
- Un número de vueltas solicitado no garantiza la existencia de una trayectoria física válida; dependerá de las efemérides, el tiempo disponible y la convergencia del optimizador.
- El optimizador de ida/vuelta emplea SciPy/DOP853, no debe describirse como RK2.
- La llegada a 120 km de altitud no modela un aterrizaje ni la reentrada atmosférica.
- No se incluyen `.git`, `node_modules`, cachés ni entornos virtuales. Si ya trabajas en el repositorio, conserva tu carpeta `.git` y revisa diferencias antes de reemplazar archivos.
