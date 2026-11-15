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
