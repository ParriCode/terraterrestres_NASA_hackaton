#set document(
  title: "ORBITAL 4B — Arquitectura actual",
  author: "Equipo ORBITAL 4B",
)

#set page(
  paper: "a4",
  margin: (x: 1.8cm, y: 1.7cm),
  numbering: "1 / 1",
)

#set text(font: "DejaVu Sans", size: 9.5pt, fill: rgb("172033"))
#set heading(numbering: "1.1")
#set par(justify: true, leading: 0.65em)
#show raw: set text(font: "DejaVu Sans Mono", size: 6.4pt)

#let navy = rgb("17365D")
#let blue = rgb("2F6FED")
#let pale-blue = rgb("EAF1FF")
#let green = rgb("197A55")
#let pale-green = rgb("E8F7F0")
#let amber = rgb("A65F00")
#let pale-amber = rgb("FFF3D8")
#let red = rgb("B42318")
#let pale-red = rgb("FDECEA")
#let gray = rgb("667085")
#let pale-gray = rgb("F4F6F8")

#show heading.where(level: 1): it => block(above: 1.1em, below: 0.55em)[
  #text(size: 16pt, weight: "bold", fill: navy)[#it.body]
  #line(length: 100%, stroke: 1pt + blue)
]

#show heading.where(level: 2): it => block(above: 0.9em, below: 0.35em)[
  #text(size: 11.5pt, weight: "bold", fill: navy)[#it.body]
]

#let status(label, color, background) = box(
  inset: (x: 5pt, y: 2pt),
  radius: 3pt,
  fill: background,
  stroke: 0.5pt + color,
)[#text(size: 7.5pt, weight: "bold", fill: color)[#label]]

#let class-box(title, body, fill: white) = block(
  width: 100%,
  inset: 7pt,
  radius: 4pt,
  fill: fill,
  stroke: 0.8pt + navy,
  breakable: false,
)[
  #align(center)[#text(weight: "bold", fill: navy)[#title]]
  #line(length: 100%, stroke: 0.5pt + rgb("98A2B3"))
  #text(size: 7.8pt)[#body]
]

#let flow-node(title, subtitle: none, fill: pale-blue, border: blue) = block(
  width: 72%,
  inset: 7pt,
  radius: 5pt,
  fill: fill,
  stroke: 0.8pt + border,
  breakable: false,
)[
  #align(center)[
    #text(weight: "bold", fill: navy)[#title]
    #if subtitle != none [
      #linebreak()
      #text(size: 7.5pt, fill: gray)[#subtitle]
    ]
  ]
]

#let down = align(center)[#text(size: 16pt, fill: blue)[↓]]

#align(center)[
  #text(size: 24pt, weight: "bold", fill: navy)[ORBITAL 4B]
  #linebreak()
  #text(size: 13pt, fill: blue)[Arquitectura y flujo del estado actual]
  #linebreak()
  #v(5pt)
  #status("DOCUMENTACIÓN VIVA", blue, pale-blue)
]

#v(10pt)

#block(inset: 9pt, radius: 5pt, fill: pale-amber, stroke: 0.6pt + amber)[
  *Alcance.* Este documento representa el repositorio tal como está ahora. El modelo
  de dominio y la carga de `bodies.json` contienen implementación. El resto de los
  módulos son, en su mayoría, esqueletos con un docstring o comentario inicial.
]

= Árbol de directorios

```text
.
├── .gitignore                         # Exclusiones de Python, React, cachés y secretos
├── README.md                          # Presentación e instrucciones generales
├── backend/
│   ├── pyproject.toml                 # Dependencias y pruebas (pendiente)
│   ├── app/
│   │   ├── __init__.py                # Declara el paquete principal
│   │   ├── main.py                    # Arranque de FastAPI (esqueleto)
│   │   ├── schemas.py                 # Contratos JSON de la API (esqueleto)
│   │   ├── config/
│   │   │   ├── __init__.py            # Declara el paquete de configuración
│   │   │   └── bodies.py              # Cuerpos de Horizons y reglas de extracción
│   │   ├── controllers/
│   │   │   ├── __init__.py            # Declara el paquete de controladores
│   │   │   └── simulation_controller.py # Endpoint de simulación (esqueleto)
│   │   ├── services/
│   │   │   ├── __init__.py            # Declara el paquete de servicios
│   │   │   ├── simulation_service.py  # Coordina una simulación (esqueleto)
│   │   │   └── diagnostics_service.py # Resume resultados (esqueleto)
│   │   ├── models/
│   │   │   ├── __init__.py            # Declara el paquete del dominio
│   │   │   └── domain.py              # Clases, enums, unidades y validaciones
│   │   ├── physics/
│   │   │   ├── __init__.py            # Declara el paquete científico
│   │   │   ├── gravity.py             # Aceleración gravitatoria (esqueleto)
│   │   │   ├── dynamics.py            # Ecuaciones de movimiento (esqueleto)
│   │   │   ├── rk2.py                 # Integrador RK2 (esqueleto)
│   │   │   └── events.py              # Impactos y encuentros (esqueleto)
│   │   └── data/
│   │       ├── __init__.py            # Declara el paquete de datos
│   │       ├── bodies.json             # Catálogo local de Tierra y Luna en SI
│   │       ├── bodies.py               # Carga el catálogo y crea CelestialBody
│   │       ├── ephemeris.py            # Posición y velocidad (esqueleto)
│   │       └── scenarios.py            # Escenarios iniciales (esqueleto)
│   └── tests/
│       ├── test_gravity.py             # Pruebas de gravedad (esqueleto)
│       ├── test_rk2.py                 # Pruebas del integrador (esqueleto)
│       ├── test_events.py              # Pruebas de eventos (esqueleto)
│       ├── test_domain.py              # Pruebas del dominio (esqueleto)
│       ├── test_ephemeris.py           # Pruebas de efemérides (esqueleto)
│       └── test_simulation_api.py      # Pruebas de la API (esqueleto)
├── frontend/
│   ├── package.json                    # Dependencias y scripts (pendiente)
│   ├── index.html                      # Página de entrada (esqueleto)
│   └── src/
│       ├── main.tsx                    # Arranque de React (esqueleto)
│       ├── App.tsx                     # Pantalla principal (esqueleto)
│       ├── components/
│       │   ├── SimulationForm.tsx      # Formulario (esqueleto)
│       │   ├── OrbitView.tsx           # Vista orbital (esqueleto)
│       │   ├── PlaybackControls.tsx    # Reproducción temporal (esqueleto)
│       │   └── ResultsPanel.tsx        # Resultados y eventos (esqueleto)
│       ├── api/simulations.ts          # Cliente HTTP (esqueleto)
│       └── types/simulation.ts         # Tipos compartidos (esqueleto)
└── docs/
    ├── main.typ                        # Fuente de este documento
    └── main.pdf                        # Documento compilado
```

== Responsabilidad y estado

#table(
  columns: (1.15fr, 2.8fr, 0.9fr),
  inset: 5pt,
  stroke: 0.4pt + rgb("D0D5DD"),
  fill: (x, y) => if y == 0 { navy } else if calc.even(y) { pale-gray } else { white },
  table.header(
    [#text(fill: white, weight: "bold")[Zona]],
    [#text(fill: white, weight: "bold")[Responsabilidad]],
    [#text(fill: white, weight: "bold")[Estado]],
  ),
  [`models/domain.py`], [Cuerpos, nave, configuración, muestras, eventos, diagnósticos y resultados.], [#status("ACTIVO", green, pale-green)],
  [`config/bodies.py`], [Tierra y Luna para Horizons, identificadores y patrones de extracción.], [#status("ACTIVO", green, pale-green)],
  [`data/bodies.py`], [Lee el JSON y devuelve un mapa `str -> CelestialBody`.], [#status("ACTIVO", green, pale-green)],
  [`data/bodies.json`], [Parámetros físicos locales y procedencia.], [#status("ACTIVO", green, pale-green)],
  [`data/ephemeris.py`], [Deberá proporcionar posición y velocidad para una fecha.], [#status("PENDIENTE", amber, pale-amber)],
  [`data/scenarios.py`], [Deberá construir origen, destino, fecha y configuración de misión.], [#status("PENDIENTE", amber, pale-amber)],
  [`physics/`], [Deberá implementar gravedad, dinámica, RK2 y eventos.], [#status("PENDIENTE", amber, pale-amber)],
  [`controllers/ + services/`], [Deberán conectar FastAPI con el núcleo científico.], [#status("PENDIENTE", amber, pale-amber)],
  [`frontend/`], [Deberá configurar, ejecutar y reproducir simulaciones.], [#status("PENDIENTE", amber, pale-amber)],
)

#pagebreak()

= Diagrama de clases

El diagrama contiene solamente las clases que existen ahora. Una flecha indica
que la clase de la izquierda contiene o utiliza la clase de la derecha.

#grid(
  columns: (1fr, 24pt, 1fr), gutter: 7pt, align: horizon,
  class-box("SimulationConfig", [
    `scenario_id: str` \
    `initial_state: SpacecraftState` \
    `duration_s: float` \
    `step_s: float`
  ], fill: pale-blue),
  align(center)[#text(size: 17pt, fill: blue)[→]],
  class-box("SpacecraftState", [
    `position_m: Vec3` \
    `velocity_m_s: Vec3` \
    _Valida dos vectores tridimensionales._
  ], fill: pale-green),

  class-box("TrajectorySample", [
    `t_s: float` \
    `spacecraft: SpacecraftState` \
    `body_positions_m: dict[str, Vec3]`
  ], fill: pale-blue),
  align(center)[#text(size: 17pt, fill: blue)[→]],
  class-box("SpacecraftState", [
    `position_m: Vec3` \
    `velocity_m_s: Vec3`
  ], fill: pale-green),

  class-box("Event", [
    `type: EventType` \
    `t_s: float` \
    `body_id: str` \
    `position_m: Vec3`
  ], fill: pale-blue),
  align(center)[#text(size: 17pt, fill: blue)[→]],
  class-box("EventType", [
    `COLLISION` \
    _Enumeración de tipos de evento._
  ], fill: pale-amber),
)

#v(8pt)

#class-box("SimulationResult", [
  #grid(
    columns: (1fr, 1fr), gutter: 10pt,
    [`config: SimulationConfig` \
     `bodies: list[CelestialBody]` \
     `status: SimulationStatus` \
     `samples: list[TrajectorySample]`],
    [`events: list[Event]` \
     `diagnostics: Diagnostics` \
     `schema_version: str` \
     `frame: str` · `units: dict`],
  )
], fill: pale-blue)

#align(center)[#text(size: 16pt, fill: blue)[↓ contiene]]

#grid(
  columns: (1fr, 1fr, 1fr), gutter: 7pt,
  class-box("CelestialBody", [
    `id: str` \
    `name: str` \
    `mu_m3_s2: float` \
    `radius_m: float` \
    `mass: float`
  ], fill: pale-green),
  class-box("Diagnostics", [
    `final_time_s: float` \
    `steps_completed: int` \
    `min_distance_m: dict` \
    `min_altitude_m: dict`
  ], fill: pale-green),
  class-box("SimulationStatus", [
    `COMPLETED` \
    `COLLISION` \
    `NUMERICAL_ERROR`
  ], fill: pale-amber),
)

#v(8pt)

#grid(
  columns: (1fr, 24pt, 1fr), gutter: 7pt, align: horizon,
  class-box("HorizonsBodyConfig", [
    `id`, `name`, `horizons_id` \
    `radius_pattern`, `mass_pattern` \
    `mass_scale_kg`
  ], fill: pale-amber),
  align(center)[#text(size: 17pt, fill: blue)[⇢]],
  class-box("bodies.json → CelestialBody", [
    `load_bodies()` recorre el catálogo, crea cada objeto y lo indexa por su identificador.
  ], fill: pale-gray),
)

== Relaciones principales

- `SimulationResult` agrega los objetos producidos por una ejecución.
- `SimulationConfig` y `TrajectorySample` contienen un `SpacecraftState`.
- `Event` utiliza `EventType`; `SimulationResult` utiliza `SimulationStatus`.
- `load_bodies()` transforma `bodies.json` en objetos `CelestialBody`.
- Todavía no existe una clase de escenario con origen, destino y fecha.

#pagebreak()

= Diagrama de control actual

Este flujo corresponde a la única ruta ejecutable implementada actualmente:
la carga del catálogo mediante `load_bodies()`.

#align(center)[
  #flow-node("Inicio", subtitle: "Una parte del programa solicita los cuerpos")
  #down
  #flow-node("load_bodies(catalog_path)", subtitle: "data/bodies.py")
  #down
  #flow-node("¿Existe bodies.json?", subtitle: "catalog_path.exists()", fill: pale-amber, border: amber)
]

#grid(
  columns: (1fr, 1fr), gutter: 18pt,
  [#align(center)[
    #text(weight: "bold", fill: red)[NO] #linebreak()
    #text(size: 15pt, fill: red)[↓]
    #flow-node("FileNotFoundError", subtitle: "La ejecución termina", fill: pale-red, border: red)
  ]],
  [#align(center)[
    #text(weight: "bold", fill: green)[SÍ] #linebreak()
    #text(size: 15pt, fill: green)[↓]
    #flow-node("Abrir y leer JSON", subtitle: "json.load(file)", fill: pale-green, border: green)
  ]],
)

#align(center)[
  #text(size: 16pt, fill: blue)[↓]
  #flow-node("Recorrer catalog['bodies']", subtitle: "Una entrada por identificador")
  #down
  #flow-node("Construir CelestialBody", subtitle: "CelestialBody(**body_data)")
  #down
  #flow-node("¿Cumple las validaciones?", subtitle: "id, name, GM y radio", fill: pale-amber, border: amber)
]

#grid(
  columns: (1fr, 1fr), gutter: 18pt,
  [#align(center)[
    #text(weight: "bold", fill: red)[NO] #linebreak()
    #text(size: 15pt, fill: red)[↓]
    #flow-node("ValueError", subtitle: "Dato vacío, no finito o no positivo", fill: pale-red, border: red)
  ]],
  [#align(center)[
    #text(weight: "bold", fill: green)[SÍ] #linebreak()
    #text(size: 15pt, fill: green)[↓]
    #flow-node("Guardar en el mapa", subtitle: "bodies[body_id] = CelestialBody", fill: pale-green, border: green)
  ]],
)

#align(center)[
  #text(size: 16pt, fill: blue)[↓]
  #flow-node("¿Quedan cuerpos por procesar?", fill: pale-amber, border: amber)
]

#grid(
  columns: (1fr, 1fr), gutter: 18pt,
  [#align(center)[
    #text(weight: "bold", fill: blue)[SÍ → repetir]
    #linebreak()
    #text(size: 8pt, fill: gray)[Construir el siguiente `CelestialBody`]
  ]],
  [#align(center)[
    #text(weight: "bold", fill: green)[NO] #linebreak()
    #text(size: 15pt, fill: green)[↓]
    #flow-node("Devolver dict[str, CelestialBody]", subtitle: "Tierra y Luna por id", fill: pale-green, border: green)
  ]],
)

== Flujo completo previsto por la estructura

Los nombres de los módulos anticipan el siguiente recorrido, pero todavía no está
implementado:

#align(center)[
  #flow-node("React", subtitle: "Formulario de simulación")
  #down
  #flow-node("FastAPI", subtitle: "schemas → controller → service")
  #down
  #flow-node("Escenario y efemérides", subtitle: "origen, destino, fecha y estados")
  #down
  #flow-node("Núcleo físico", subtitle: "gravedad → dinámica → RK2 → eventos")
  #down
  #flow-node("Diagnóstico y respuesta", subtitle: "SimulationResult → React")
]

#block(inset: 8pt, radius: 4pt, fill: pale-amber, stroke: 0.6pt + amber)[
  *Próximo punto de diseño:* crear la clase que represente un escenario o
  simulación con `CelestialBody` de origen, `CelestialBody` de destino y una fecha;
  después implementar `data/scenarios.py` y `data/ephemeris.py` alrededor de ese
  contrato.
]
