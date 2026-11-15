# ORBITAL4B | Complete Project

This ZIP contains the complete project built from the unified version and the new fixed lunar stay time control.

## Contents
- `backend/`: FastAPI, missions, optimizer, simulation, ephemerides, and tests.
- `frontend/`: React/TypeScript, components, styles, types, and SVG.
- `run.py`: simultaneous startup of the backend and frontend on Windows and Linux.
- `README.md`: operation, routes, and known limitations.
- `.gitignore`: standard exclusions for Python and Node.

## First Startup
From the root of the extracted folder:

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

## Tests
From `backend/`:
```bash
python -m pytest tests/test_mission_contract.py tests/test_lunar_orbit_return.py -q
```
From `frontend/`:
```bash
npm run build
```

## Notes
- The Apollo 11 form asks for a lunar orbit stay time (hours), in addition to the altitude.
- The engine respects the requested fixed duration. The number of orbits is calculated and displayed after integrating the trajectory.
- The requested time does not guarantee a valid physical solution; it will depend on the ephemerides, the total window, and the optimizer's convergence.
- The round-trip optimizer uses SciPy/DOP853, it should not be described as RK2.
- Arrival at 120 km altitude does not model a landing or atmospheric reentry.
- `.git`, `node_modules`, caches, and virtual environments are not included. If you are already working in the repository, keep your `.git` folder and review differences before replacing files.