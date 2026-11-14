# TERRATERRESTRES

 - `Jose Luis Parrilla Fuente`
 - `Rafael Juan Jimenez`
 - `Alejandro Moreno Lechado`

 Nuestro proyecto tratará de realizar un modelo de enrutamiento espacial en el sistema solar. Encontrar la ruta optima en un determinado punto del sistema solar hacia otro punto del sistema solar dadas también restricciones de tiempo, velocidad o peso.

## Ejemplo con Astropy

Desde la raíz del proyecto:

```bash
python3 -m venv src/.venv
src/.venv/bin/python -m pip install -r requirements.txt
src/.venv/bin/python src/main.py
```

El programa muestra la distancia entre los centros de la Tierra y la Luna en
AU (unidades astronómicas), kilómetros y metros para el instante actual en UTC.
La distancia varía con la fecha. Usa las efemérides aproximadas incluidas en
Astropy (`builtin`), sin descargar efemérides adicionales.
