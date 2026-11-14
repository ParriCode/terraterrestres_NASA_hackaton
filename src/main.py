"""Muestra la distancia actual entre los centros de la Tierra y la Luna."""

from astropy import units as u
from astropy.coordinates import get_body_barycentric
from astropy.time import Time


def main():
    instante = Time.now()
    tierra = get_body_barycentric("earth", instante, ephemeris="builtin")
    luna = get_body_barycentric("moon", instante, ephemeris="builtin")
    distancia = (luna - tierra).norm()

    print(f"Distancia Tierra–Luna ({instante.utc.isot} UTC)")
    print(f"AU: {distancia.to_value(u.au):.10f}")
    print(f"km: {distancia.to_value(u.km):.3f}")
    print(f"m:  {distancia.to_value(u.m):.3f}")


if __name__ == "__main__":
    main()
