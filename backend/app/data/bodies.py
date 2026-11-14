"""Carga y construcción de los cuerpos del catálogo local."""

import json
from pathlib import Path



from app.models.domain import CelestialBody


CATALOG_PATH = Path(__file__).with_name("bodies.json")


def load_bodies(
    catalog_path: Path = CATALOG_PATH,
) -> dict[str, CelestialBody]:
    """Carga los cuerpos indexados por su identificador."""
    if not catalog_path.exists():
        raise FileNotFoundError(
            f"El catálogo de cuerpos no existe: {catalog_path}"
        )

    with catalog_path.open(encoding="utf-8") as file:
        catalog = json.load(file)

    bodies = {
        body_id: CelestialBody(
            id=body_data["id"],
            name=body_data["name"],
            mu_m3_s2=body_data["mu_m3_s2"],
            radius_m=body_data["radius_m"],
        )
        for body_id, body_data in catalog["bodies"].items()
    }

    return bodies
