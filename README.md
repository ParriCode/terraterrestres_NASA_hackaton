<div align="center">

# 🚀 ORBITAL 4B 🚀

### De la Tierra a la Luna, una trayectoria cada vez.

**Diseño y visualización de transferencias orbitales con efemérides de NASA/JPL Horizons.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Equipo](https://img.shields.io/badge/Equipo-Terraterrestres-8B5CF6)

[Configura tu viaje](#-configura-tu-viaje) · [Explora el resultado](#-explora-el-resultado) · [Puesta en marcha](#-puesta-en-marcha) · [Equipo](#-equipo)

</div>

---

## 🚨 La misión

¿Como poder visualizar un viaje espacial de forma intuitiva ? ¿ Somos conscientes de lo de que implica realmente viajar al espacio ?  


Desde el equipo de **Terraterrestres** presentamos **ORBITAL 4B**. Que ofrece una visión visual e intuitiva de estar preguntas materializada en un prototipo de transferencia **Tierra–Luna**: 

## 🚨 Configura tu viaje

Estos son los datos que puedes cambiar en la aplicación:

| Opción | ¿Qué significa? |
| --- | --- |
| **Fecha de salida (UTC)** | La fecha de lanzamiento, **LAS POSICIONES DE LOS ASTROS CAMBIAN CON LA FECHA !!** |
| **Duración (días)** | En cuanto tiempo queremos completar la misión. |
| **Mínima energía** | Prioriza la trayectoria válida encontrada que requiere menos energía de lanzamiento. |
| **Mínima distancia** | Prioriza la trayectoria válida encontrada con menor recorrido. |

Los ángulos indican **lugares de salida y llegada**, no la inclinación del cohete. 

## 🚨 Explora el resultado

Pulsa **«Calcular transferencia»** para obtener el recorrido usando las posiciones de la Tierra y la Luna de NASA/JPL Horizons. Después puedes reproducir el viaje, pausarlo, cambiar la velocidad y moverte por el tiempo.

La aplicación muestra la **velocidad y energía necesarias para salir**, la **distancia recorrida** y el **error de llegada**: cuánto se aleja el punto final calculado del destino elegido.

## 🚨 Sistema solar y datos NASA

Puedes elegir **origen y destino** entre el Sol, los ocho planetas y la Luna, usando los selectores o **«Elegir en el mapa»** y pulsando un cuerpo. La fecha determina sus posiciones; la duración indica el tiempo disponible para llegar y la masa permite calcular la energía de lanzamiento.

Las posiciones y velocidades se consultan en [NASA/JPL Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) para la fecha y el intervalo del viaje. Los radios medios y parámetros gravitatorios proceden de las fichas de los cuerpos del mismo servicio y se guardan, con su fuente y fecha de consulta, en [el catálogo solar](backend/app/data/solar_bodies.json).

Para acelerar la vista, descargamos muestras horarias de cada día y mostramos los cuerpos conforme llegan. Los cambios de hora se interpolan en el navegador sin volver a consultar NASA. Las respuestas se guardan en el servidor hasta siete días, incluso tras reiniciarlo. Las peticiones simultáneas de los usuarios comparten las descargas; el acceso a JPL respeta su [límite de una consulta a la vez](https://ssd-api.jpl.nasa.gov/doc/index.php).

La vista solar proyecta esos datos en 2D y comprime las distancias para facilitar la selección; los iconos están ampliados. Si NASA no responde, se muestra el error, sin sustituir sus datos por posiciones inventadas.

**Modelo simplificado:** sobre la nave solo actúa la gravedad del origen y del destino. El Sol solo influye si es uno de los seleccionados. Los cuerpos siguen las efemérides NASA; la trayectoria de la nave la calcula nuestra aplicación. La llegada es al radio nominal del destino, sin modelar atmósferas, combustible ni captura orbital. Para los gigantes gaseosos y el Sol, ese radio no representa suelo sólido.

Se admiten viajes de hasta 100 años, sujetos a la cobertura de Horizons. La salida se orienta automáticamente hacia una estimación del encuentro y se busca el ángulo de llegada. La búsqueda tiene tiempo limitado y puede no encontrar una solución; no garantiza la ruta óptima ni una misión físicamente viable en el sistema solar completo. El modo de órbita lunar y regreso conserva su límite de 30 días.

## 🚨 Puesta en marcha

Necesitas Python 3.10 o superior, Node.js compatible con Vite 8 e internet para consultar los datos de NASA.

Desde la raíz del proyecto, arranca el servidor:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m uvicorn app.main:app --reload
```

En otra terminal, desde la raíz, abre la interfaz:

```bash
cd frontend
npm ci
npm run dev
```

Entra en **<http://localhost:5173>**. Con esta configuración local no necesitas cambiar ninguna variable adicional.

📄 [Memoria del proyecto](docs/main.pdf) · [Documentación técnica](backend/TRANSFER.md)

## 🚨 Equipo

**Terraterrestres**

- Jose Luis Parrilla Fuente
- Rafael Juan Jimenez
- Alejandro Moreno Lechado
- Yaojian Li

---

<div align="center">

**🌍 Tierra → Trayectoria → Luna 🌙**

*Una herramienta para explorar el viaje, entender el modelo y experimentar con la misión.*

</div>
