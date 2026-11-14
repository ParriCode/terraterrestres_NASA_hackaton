"""Punto de entrada de FastAPI."""
from fastapi import FastAPI

app = FastAPI(
    title="ORBITAL 4B",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}