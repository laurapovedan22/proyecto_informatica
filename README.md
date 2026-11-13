# Lumina · Sprint 2

Entrega del **Sprint 2 (2–15 de noviembre de 2026)** de Lumina, la plataforma IoT de
supervisión de un supermercado y su parking (Proyecto de Ingeniería Informática 1 ·
Universidad Europea · 2026-27). Añade cuatro historias, **32 horas**, sobre la entrega
completa del Sprint 1, cuyo acceso por roles, gestión de usuarios y perfil se conservan,
incluido el bloqueo de la cuenta tras tres contraseñas incorrectas seguidas, que solo el
administrador puede desbloquear desde «Usuarios».

**Ampliación del 04/11/2026** ([detalle](docs/sprint-2.md#ampliación-del-04112026-superadministrador-cámaras-con-vídeo-y-datos-en-vivo)):

- **Superadministrador.** Los administradores ya no se pueden modificar entre sí: solo el
  superadministrador gestiona los perfiles y permisos de los administradores, sus datos, su
  activación («cerrar la cuenta») y su desbloqueo, y solo él asigna el perfil de administrador.
- **Cámaras funcionales.** Cada cámara reproduce un vídeo real de videovigilancia de Internet
  (interior de una tienda y aparcamiento), con rótulo «EN DIRECTO» y hora que avanza.
- **Datos en vivo.** La aplicación simula continuamente las lecturas de los sensores, así que
  aforo, parking, temperatura, humedad, distancia y detecciones cambian en cada refresco.

| Historia | Contenido | Dónde |
| -------- | --------- | ----- |
| H2.1 · RF-04 / RNF-03 | Lectura JSON, valores con unidad y hora, estado Activo / Error / Desactualizado / Sin datos | `controllers/analysis.py`, `controllers/supervision.py`, `views/pages/supervision.py` |
| H2.2 · RF-05 | Contadores virtuales de personas y vehículos; aforo, plazas ocupadas y libres acotadas a la capacidad | `controllers/facility.py`, `views/components/facility.py` |
| H2.3 · RF-06 | Temperatura en °C y humedad en %, hora de lectura y actualización sin recargar | `views/pages/dashboard.py`, `views/pages/base.py` (`LiveData`) |
| H2.4 · RF-07 | Cámaras con vídeo en directo desde URL (o imagen / vista simulada) y detecciones por zona; acceso para seguridad y administración | `views/components/camera.py`, `views/pages/supervision.py`, `views/routes.py` |

Todos los perfiles ven los indicadores del establecimiento. Seguridad y administración
ven además el resumen de sensores y el menú «Supervisión». Administración conserva el
resumen y la gestión de cuentas. Las funciones futuras siguen identificadas por su sprint,
sin pantallas ni lógica de alertas, actuadores, configuración, históricos o actividad.

## Puesta en marcha

Esta entrega **crea su propio entorno virtual** en `lumina-sprint2/.venv`; no se copia ni
se depende del entorno del Sprint 1 para utilizarla:

```bash
cd /ruta/a/lumina-sprint2
python3.13 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py           # abre la ventana de escritorio de Lumina
```

Aplicación de escritorio con Python 3.13, NiceGUI 3.18 y pywebview; se mantiene la
compatibilidad del código y de las herramientas con Python 3.11 o posterior.

Al ejecutar desde el código, la primera vez se copian los datos de ejemplo de `data/` en
`datos-locales/` (ignorada por git) y la aplicación trabaja sobre esa copia, porque con los datos
en vivo escribe continuamente. `data/` no se modifica: la usan los tests y el ejecutable. Para
volver a empezar con los datos de ejemplo, basta con borrar `datos-locales/`.
Cuentas de demostración:

| Perfil | Correo | Contraseña |
| --- | --- | --- |
| Superadministrador | `elena.navarro@lumina.es` | `superadmin123` |
| Administrador | `ana.lopez@lumina.es` | `admin123` |
| Administrador | `javier.moreno@lumina.es` | `admin123` |
| Seguridad | `carlos.ruiz@lumina.es` | `seguridad123` |
| Gerente | `marta.garcia@lumina.es` | `gerente123` |

Jerarquía: superadministrador > administrador > seguridad y gerencia. Cada cuenta solo modifica
cuentas de rango inferior al suyo, así que Ana y Javier no pueden tocarse entre sí y es Elena
quien gestiona a los administradores. El perfil de superadministrador no se asigna ni se modifica
desde la aplicación.

Tres contraseñas incorrectas seguidas bloquean la cuenta. Las de administración las desbloquea
el superadministrador; si se bloquea su cuenta, se recupera editando `usuarios.json` en la
carpeta de datos (`datos-locales/` desde el código): `"bloqueado": false` e
`"intentos_fallidos": 0` en esa cuenta.

Para usar el modo navegador opcional: `LUMINA_NATIVE=false python main.py`.

## Simulación y demostración

**Datos en vivo (por defecto).** Mientras no haya maqueta física, la aplicación genera ella misma
una lectura nueva de cada sensor operativo en cada refresco (`LUMINA_REFRESH_SECONDS`, 5 s): las
pantallas nunca muestran siempre el mismo dato. Los valores son verosímiles (afluencia según la
hora, temperatura y humedad estables con un ciclo diario, coches en el acceso, detecciones
breves) y no se tocan los sensores sin lectura, en error o desactualizados. Si otra fuente escribe
un sensor, la simulación se lo deja durante dos minutos desde su última escritura.
`LUMINA_SIMULATION=false python main.py` arranca sin simulación y muestra solo lo que hay en los JSON.

**Cámaras.** Los datos de ejemplo apuntan a dos grabaciones reales de videovigilancia de dominio
público en Wikimedia Commons (interior de una tienda y aparcamiento); se ven con conexión a
Internet y cada cámara puede apuntar a cualquier otra URL de vídeo, imagen o MJPEG en
`sensores.json`. Sin conexión, la cámara indica «Sin señal de vídeo».

**Simulador externo.** Con la aplicación en una terminal y el mismo entorno activado en otra:

```bash
python scripts/simular_sensores.py --intervalo 3 --semilla 7 --movimiento
```

El simulador escribe mediante los repositorios en `sensores.json` de la misma carpeta de datos
que la aplicación (`datos-locales/` por defecto); el dashboard y la supervisión releen los datos
cada cinco segundos, sin recarga. `LUMINA_REFRESH_SECONDS`
permite cambiar ese intervalo al arrancar la aplicación. Sin `--movimiento` se conservan
las detecciones existentes. `--ciclos 10` limita la ejecución; Ctrl+C la detiene.

Para una demostración repetible, trabajar sobre una copia de `data/`: configurar
`LUMINA_DATA_DIR` al arrancar la aplicación y pasar esa misma carpeta con `--datos` al
simulador. Los datos iniciales mantienen el instante del Sprint 1 (14/10/2026, 14:30), que se
ven tal cual con `LUMINA_SIMULATION=false`; la vigencia está desactivada por defecto
(`antiguedad_maxima_lectura_min: null`).

1. Entrar como gerente y mostrar aforo, plazas, temperatura y humedad con unidades y horas.
2. Lanzar el simulador y observar la actualización automática.
3. Entrar como seguridad, mostrar el resumen de sensores y abrir «Supervisión».
4. Mostrar el vídeo en directo de las cámaras de almacén y parking, detecciones por zona y
   valores/estados de sensores.
5. Verificar el mismo acceso con administración y el rechazo de `/supervision` con gerente. En
   «Usuarios», mostrar que Ana no puede modificar a Javier ni a Elena y que Elena sí gestiona a
   los administradores.
6. Mostrar los estados Sin datos / Error / Desactualizado siguiendo el
   [guion detallado](docs/sprint-2.md), y cerrar sesión.

## Documentación

- [Sprint 2: criterios literales, tareas, pruebas y guion](docs/sprint-2.md).
- [Entrega y auditoría del Sprint 1, conservadas](docs/sprint-1.md).
- [Arquitectura MVC y flujo simulador → JSON → LiveData](docs/arquitectura.md).
- [Diagramas UML de las clases](docs/uml-clases.md).
- [Esquemas JSON y campos documentados](docs/esquemas-json.md).
- [Capturas del Sprint 2](docs/capturas/sprint-2) y [del Sprint 1](docs/capturas).

Para regenerar el contrato documentado (solo biblioteca estándar):

```bash
python scripts/documentar_esquemas.py
```

## Calidad

Con el entorno propio instalado:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/mypy
.venv/bin/ruff check .
```

Durante la preparación de esta copia, que todavía no tiene `.venv`, la verificación utiliza
el entorno ya instalado del Sprint 1, sin modificarlo:

```bash
../lumina-sprint1/.venv/bin/python -m pytest -q -p no:cacheprovider
../lumina-sprint1/.venv/bin/mypy
../lumina-sprint1/.venv/bin/ruff check .
```

Los tests usan copias temporales de los datos y la simulación de NiceGUI sin ventana ni
navegador, con los datos en vivo desactivados salvo en las pruebas que los comprueban. Incluyen
permisos y jerarquía de cuentas, refresco de lecturas JSON, límites de contadores, simulación en
vivo, cámaras, esquema del simulador y vigencia de la documentación. Véase el resultado en
[sprint-2.md](docs/sprint-2.md).

## Ejecutable

`python scripts/empaquetar.py` prepara `dist/Lumina Sprint 2.app` en macOS o la carpeta del
programa en Windows (generándola en Windows). Identificador: `es.lumina.sprint2`. Los datos
se separan de otras entregas en `~/Library/Application Support/Lumina Sprint 2` (macOS),
`%APPDATA%\Lumina Sprint 2` (Windows) o `~/.local/share/lumina-sprint-2` (Linux).
El empaquetado y la apertura de la ventana quedan fuera de esta verificación automatizada.
El ejecutable de `dist/` es anterior a la ampliación del 04/11/2026: para incluir superadministrador,
cámaras con vídeo y datos en vivo hay que regenerarlo. Una carpeta de datos que ya existía conserva
sus cuentas y cámaras; las nuevas cuentas de demostración aparecen con una carpeta de datos nueva.
`dist/Lumina Sprint 2.app` se regeneró el 31/10/2026, ya con el bloqueo por intentos fallidos, y
se comprobó a mano en macOS: abre su ventana, bloquea una cuenta tras tres contraseñas incorrectas,
el administrador la desbloquea y al cerrar la ventana no quedan sesiones abiertas.
