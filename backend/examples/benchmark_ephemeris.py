"""Mide latencia real de Horizons y consultas locales con caché.

Desde la raíz:
    PYTHONPATH=backend python3 backend/examples/benchmark_ephemeris.py
"""

import argparse
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from time import perf_counter

from app.data.bodies import load_bodies
from app.data.ephemeris import (
    EphemerisError,
    _fetch_state,
    get_body_time_pos,
    get_body_time_velocity,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3, help="Peticiones reales por cuerpo.")
    parser.add_argument("--cached-calls", type=int, default=1000)
    args = parser.parse_args()
    if args.samples < 1 or args.cached_calls < 1:
        parser.error("Los contadores deben ser mayores que cero.")

    bodies = load_bodies()
    epoch = datetime(2026, 11, 14, tzinfo=timezone.utc)
    _fetch_state.cache_clear()
    failures = 0
    network_times = []
    print("Latencia de efemérides: red + lectura + conversión; peticiones secuenciales.")
    for body in bodies.values():
        for index in range(args.samples):
            instant = epoch + timedelta(seconds=index * 60)
            start = perf_counter()
            try:
                get_body_time_pos(body, instant)
            except EphemerisError as error:
                failures += 1
                print(f"ERROR {body.id}: {perf_counter() - start:.3f} s — {error}", flush=True)
                continue
            elapsed = perf_counter() - start
            network_times.append(elapsed)
            print(f"RED {body.id} muestra {index + 1}: {elapsed * 1000:.2f} ms", flush=True)

            # La velocidad del mismo instante debe reutilizar el estado descargado.
            before = _fetch_state.cache_info()
            start = perf_counter()
            for _ in range(args.cached_calls):
                get_body_time_pos(body, instant)
                get_body_time_velocity(body, instant)
            cached_elapsed = perf_counter() - start
            after = _fetch_state.cache_info()
            calls = args.cached_calls * 2
            assert after.misses == before.misses, "Las llamadas repetidas consultaron la red."
            assert after.hits - before.hits == calls
            print(f"  CACHÉ: {cached_elapsed / calls * 1e6:.2f} µs/llamada ({calls} llamadas)")

    if network_times:
        print(
            f"\nRED ({len(network_times)} éxitos, {failures} errores): "
            f"media={mean(network_times):.3f} s, mediana={median(network_times):.3f} s, "
            f"mín={min(network_times):.3f} s, máx={max(network_times):.3f} s"
        )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
