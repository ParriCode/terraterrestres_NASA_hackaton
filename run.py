#!/usr/bin/env python3
"""Arranca FastAPI y React/Vite en Windows, Linux o macOS.

Uso desde la raíz: python run.py
Opcional: python run.py --backend-only / --frontend-only / --install
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # npm invoca un shell y crea un proceso hijo; /T los detiene juntos.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ORBITAL4B: FastAPI + Vite")
    parser.add_argument("--backend-only", action="store_true", help="Solo FastAPI")
    parser.add_argument("--frontend-only", action="store_true", help="Solo React")
    parser.add_argument("--install", action="store_true", help="Instalar dependencias npm si faltan")
    parser.add_argument("--no-reload", action="store_true", help="Desactivar autorecarga de FastAPI")
    args = parser.parse_args(argv)
    if args.backend_only and args.frontend_only:
        parser.error("Elige --backend-only o --frontend-only, no ambos")
    if not (BACKEND / "app" / "main.py").is_file() or not (FRONTEND / "package.json").is_file():
        print("Error: ejecuta este archivo desde un repositorio que contenga backend/ y frontend/.", file=sys.stderr)
        return 2

    need_backend = not args.frontend_only
    need_frontend = not args.backend_only
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm") if need_frontend else None
    if need_frontend and not npm:
        print("Error: no encuentro npm en PATH. Instala Node.js LTS.", file=sys.stderr)
        return 2
    if need_frontend and not (FRONTEND / "node_modules").exists():
        if not args.install:
            print("Faltan dependencias React. Ejecuta 'cd frontend && npm ci' o 'python run.py --install'.", file=sys.stderr)
            return 2
        print("Instalando dependencias frontend con npm ci…", flush=True)
        result = subprocess.run([npm, "ci"], cwd=FRONTEND, check=False)
        if result.returncode != 0:
            return result.returncode

    processes: list[subprocess.Popen] = []
    # También limpiar procesos hijos si el lanzador recibe SIGTERM (p. ej.
    # desde un gestor de procesos Linux); Ctrl+C lanza KeyboardInterrupt.
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    def handle_shutdown(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, handle_shutdown)
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        if need_backend:
            cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
            if not args.no_reload:
                cmd.append("--reload")
            print("[backend] http://127.0.0.1:8000/docs", flush=True)
            processes.append(subprocess.Popen(cmd, cwd=BACKEND, **kwargs))
        if need_frontend:
            print("[frontend] http://localhost:5173/", flush=True)
            processes.append(subprocess.Popen([npm, "run", "dev", "--", "--host", "127.0.0.1"], cwd=FRONTEND, **kwargs))
        print("Pulsa Ctrl+C para detener ambos servidores.", flush=True)
        while True:
            for proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"Un servidor terminó con código {code}. Cerrando el resto.", file=sys.stderr)
                    return code if code else 0
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nCerrando servidores…", flush=True)
        return 0
    finally:
        for proc in reversed(processes):
            _stop(proc)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())
