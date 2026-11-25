# Lumina · Sprint 3

Entrega del **Sprint 3 (16–29 de noviembre de 2026)**: cuatro historias, **30 horas**,
sobre la entrega completa del Sprint 2. Plataforma IoT de supervisión de un supermercado
y su parking, Proyecto de Ingeniería Informática 1 · Universidad Europea · 2026-27.

| Historia | Función añadida | Implementación principal |
| --- | --- | --- |
| H3.1 · RF-08 | Configuración de umbrales, capacidad, vigencia y zonas restringidas, solo administración | `controllers/configuration.py`, `views/pages/configuration.py`, `/configuracion` |
| H3.2 · RF-09 | Alertas por temperatura crítica, movimiento restringido y fallo de sensor; avisos emergentes; LED y alarma simulados | `controllers/rules.py`, `views/components/shell.py`, `views/components/incidents.py` |
| H3.3 · RF-10 | Ventilación automática con histéresis, control manual y retorno a automático | `controllers/rules.py`, `controllers/supervision.py`, Supervisión |
| H3.4 · RF-11 | Listado y detalle de alertas, revisión y resolución conservando el responsable | `controllers/supervision.py`, Supervisión › Alertas |

Se conservan el acceso, los usuarios y el perfil del Sprint 1 (incluido el bloqueo de la
cuenta tras tres contraseñas incorrectas seguidas, que solo el administrador desbloquea desde
«Usuarios»), y los sensores, cámaras, aforo, parking y ambiente del Sprint 2. Históricos, estadísticas y registros de actividad
permanecen fuera de alcance. No se añaden `ActivityLog` ni `registros.json`.

**Ampliación del 04/11/2026** ([detalle](docs/sprint-3.md#ampliación-del-04112026-superadministrador-cámaras-con-vídeo-y-datos-en-vivo)),
igual que en el Sprint 2:

- **Superadministrador.** Los administradores ya no se pueden modificar entre sí: solo el
  superadministrador gestiona los perfiles y permisos de los administradores, sus datos, su
  activación («cerrar la cuenta») y su desbloqueo, y solo él asigna el perfil de administrador.
- **Cámaras funcionales.** Cada cámara reproduce un vídeo real de videovigilancia (interior de
  una tienda y aparcamiento), con rótulo «EN DIRECTO» y hora que avanza.
- **Datos en vivo.** La aplicación simula continuamente las lecturas de los sensores; las reglas
  las evalúan como las de la maqueta, así que también aparecen alertas por movimiento en zonas
  restringidas y el ventilador automático reacciona a la temperatura.

**Ampliación del 18/11/2026: análisis de imagen con YOLO** ([detalle](docs/sprint-3.md#ampliación-del-18112026-análisis-de-imagen-con-yolo)).
En cada refresco, YOLO busca personas en un fotograma de cada cámara. Funciona como un sensor de
movimiento de la zona de la cámara: si ve a alguien en una **zona restringida**, se enciende un
piloto rojo sobre la imagen, las reglas encienden el **LED de aviso y la alarma** de la zona y abren
una alerta «Persona en zona restringida» con la **imagen marcada** (las personas recuadradas).
En las zonas no restringidas solo se cuentan las personas.

## Uso

Python 3.13, NiceGUI 3.18 o 3.19 y pywebview; compatible con Python ≥ 3.11. `requirements.txt`
incluye `ultralytics` (YOLO), que instala también PyTorch y OpenCV (unos 150 MB en macOS; más en
Windows y Linux). Para instalar un entorno propio de esta entrega:

```bash
cd /ruta/a/lumina-sprint3
python3.13 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py           # abre la ventana de escritorio
```

La primera vez que analiza imágenes descarga en `descargas/` (ignorada por git) el modelo
`yolo26n.pt` (5 MB); hace falta conexión solo esa vez. Sin `ultralytics` la aplicación funciona
igual y Supervisión indica que el análisis no está disponible.

Estos comandos son instrucciones de uso manual; la preparación y los tests no abren
ventanas ni navegadores. El modo nativo de escritorio es el predeterminado.

Al ejecutar desde el código, la primera vez se copian los datos de ejemplo de `data/` en
`datos-locales/` (ignorada por git) y la aplicación trabaja sobre esa copia, porque con los datos
en vivo escribe continuamente. `data/` no se modifica: la usan los tests y el ejecutable. Para
volver a empezar con los datos de ejemplo, basta con borrar `datos-locales/`.

| Perfil | Correo | Contraseña de demostración |
| --- | --- | --- |
| Superadministrador | `elena.navarro@lumina.es` | `superadmin123` |
| Administrador | `ana.lopez@lumina.es` | `admin123` |
| Administrador | `javier.moreno@lumina.es` | `admin123` |
| Seguridad | `carlos.ruiz@lumina.es` | `seguridad123` |
| Gerente | `marta.garcia@lumina.es` | `gerente123` |

Administración configura y controla; seguridad atiende alertas y controla equipos.
El gerente consulta indicadores y estados de equipos, sin botones de control ni acceso
a `/supervision` o `/configuracion`. Cada acción revalida sesión y permisos; el controlador
vuelve a autorizar al usuario vigente dentro de la transacción.

Jerarquía: superadministrador > administrador > seguridad y gerencia. Cada cuenta solo modifica
cuentas de rango inferior al suyo, así que Ana y Javier no pueden tocarse entre sí y es Elena
quien gestiona a los administradores. El perfil de superadministrador no se asigna ni se modifica
desde la aplicación.

Tres contraseñas incorrectas seguidas bloquean la cuenta. Las de administración las desbloquea
el superadministrador; si se bloquea su cuenta, se recupera editando `usuarios.json` en la
carpeta de datos (`datos-locales/` desde el código): `"bloqueado": false` e
`"intentos_fallidos": 0` en esa cuenta.

## Reglas y refresco

Un único temporizador del **servidor**, creado en `LuminaApp`, evalúa las reglas cada
`LUMINA_REFRESH_SECONDS` (5 segundos por defecto). Las vistas usan ese mismo intervalo
para releer datos con `LiveData` y detectar alertas nuevas con `AlertWatcher`.
Con `0` se desactivan los ciclos periódicos; guardar configuración o volver a automático
sigue evaluando las reglas inmediatamente.
Las evaluaciones se ejecutan en un hilo, también desde esas acciones de usuario, para
mantener disponible el bucle de eventos. Al cerrar se cancela el temporizador y se espera
el ciclo en curso; los fallos se registran y permiten reintentar en el ciclo siguiente.

- Temperatura **≥ temperatura crítica**: alerta `temperatura_critica`.
- Movimiento operativo positivo en una zona restringida: alerta
  `movimiento_zona_restringida`, LED y alarma de esa zona encendidos en modo automático.
- Sensor en error, incluso sin valor, o con una lectura no finita: alerta `fallo_sensor`.
- Solo una alerta abierta por tipo, zona y sensor: `pendiente` o `en_revision`.
  Al resolverla se conserva y puede aparecer una nueva si la condición continúa.
- Ventilador automático: usa la mayor temperatura operativa de su zona. Enciende al
  **superar** el umbral; apaga a **umbral − 0,5 °C** o menos; mantiene el estado dentro
  de la banda o sin lecturas válidas. El modo manual se respeta hasta «Volver a automático».
- LED y alarma se pueden apagar manualmente. Si sigue habiendo movimiento restringido,
  el siguiente ciclo los reactiva. Resolver una alerta no apaga los equipos.
- Una cámara cuyo último análisis de YOLO ve personas en una zona restringida cuenta como
  movimiento de esa zona: alerta `persona_zona_restringida` (una abierta por cámara) con la
  imagen marcada, y LED y alarma de la zona encendidos en modo automático.

Las alertas se muestran con detalle en **Supervisión › Alertas**, sin una página `/alertas`
adicional. «Activa» corresponde a `pendiente` en JSON; los otros estados son «En revisión»
y «Resuelta». `atendida_por` y `actualizada_en` conservan el último cambio efectivo.
Los umbrales leídos del JSON también deben ser finitos, estar entre −10 y 60 °C y tener
la crítica por encima del umbral. Un refresco de configuración conserva las ediciones
pendientes; las páginas y el contador reintentan si los datos estaban dañados al abrirlas.

## Análisis de imagen con YOLO

`LuminaApp` ejecuta en segundo plano, cada `LUMINA_REFRESH_SECONDS`, el ciclo de
`VisionController` (`controllers/vision.py`):

1. Toma el fotograma actual de cada cámara activa (`VideoFrameReader`, con OpenCV), recorriendo el
   vídeo en bucle según la hora, como en pantalla. Las cámaras de ejemplo usan los vídeos de
   `assets/camaras/`, que la aplicación también sirve a la pantalla; un vídeo de Internet se
   descargaría una vez en `descargas/videos/`.
2. YOLO (`YoloPersonDetector`, modelo preentrenado `yolo26n.pt`) busca personas (clase *person* de COCO,
   confianza ≥ 50 %).
3. Guarda en la cámara (`sensores.json` › `camaras`) cuántas personas ve y cuándo y, si ve a
   alguien, la imagen con las personas recuadradas en `capturas/` (dentro de la carpeta de datos):
   en rojo y con el rótulo «PERSONA EN ZONA RESTRINGIDA» si la zona es restringida.
4. Las reglas (`RulesController`) lo tratan como un sensor de movimiento: en una zona restringida
   encienden el LED y la alarma y abren la alerta con la imagen, sin repetirla mientras siga abierta.

En **Supervisión**, cada cámara indica lo que ve YOLO («YOLO: 2 personas en zona restringida ·
Hoy · 18:05»), enciende un piloto rojo sobre el vídeo y permite abrir la imagen analizada. Cada
alerta de una cámara muestra su imagen. Las capturas que ya no usa ninguna cámara ni ninguna
alerta se borran a los dos minutos; las de las alertas se conservan como prueba.

| Variable | Por defecto | Uso |
| --- | --- | --- |
| `LUMINA_VISION` | `true` | `false` desactiva el análisis de imagen |
| `LUMINA_YOLO_MODEL` | `yolo26n.pt` | otro modelo de ultralytics (p. ej. `yolo26s.pt`, más preciso y lento) o la ruta de un `.pt` |

Para analizar una foto concreta como si la hubiera captado una cámara (por ejemplo, en una
demostración con `LUMINA_VISION=false`):

```bash
python scripts/analizar_imagen.py --datos /tmp/lumina-sprint3-demo --camara cam-almacen --imagen foto.jpg
python scripts/analizar_imagen.py --datos /tmp/lumina-sprint3-demo --camara cam-almacen --ejemplo
```

`--ejemplo` usa la foto de un autobús con cuatro peatones que trae ultralytics. El análisis de un
programa externo manda durante dos minutos sobre el análisis en vivo, igual que los escenarios del
simulador. Se desactivan la telemetría, los avisos de versión y las instalaciones automáticas de
ultralytics (`YOLO_OFFLINE=1`); solo se conecta para descargar el modelo y los vídeos. ultralytics
y sus modelos tienen licencia AGPL-3.0, válida para este proyecto académico.

## Simulación

**Datos en vivo (por defecto).** Mientras no haya maqueta física, la aplicación genera ella misma
una lectura nueva de cada sensor operativo en cada refresco: afluencia según la hora, temperatura
y humedad estables con un ciclo diario, coches en el acceso y detecciones breves, todas con su
hora actual. Las reglas las evalúan como las de la maqueta: una detección en una zona restringida
abre una alerta (una sola abierta por sensor) y enciende LED y alarma de su zona. No se tocan los
sensores sin lectura, en error o desactualizados, y si el simulador de terminal (o la maqueta)
escribe un sensor, la simulación se lo deja durante dos minutos desde su última escritura: los
escenarios funcionan igual. `LUMINA_SIMULATION=false` arranca sin simulación; el guion de
demostración paso a paso la desactiva para que cada escenario sea determinista.

**Cámaras.** Los datos de ejemplo usan dos grabaciones reales de videovigilancia de dominio
público de Wikimedia Commons ([interior de una tienda](https://commons.wikimedia.org/wiki/File:HD_CCTV_Camera_video_3MP_4MP_iProx_CCTV_HDCCTVCameras.net_retail_store.webm)
y [aparcamiento](https://commons.wikimedia.org/wiki/File:BLK-HDPTZ12_Security_Camera_Parking_Lot_Surveillance_Video.webm),
480p WebM). Desde el 18/11/2026 se guardan en `assets/camaras/` y la aplicación las sirve en
`/assets/camaras/…`: se ven sin conexión y YOLO analiza el mismo fichero (Wikimedia rechaza que un
programa descargue sus vídeos). Cada cámara puede apuntar a otra URL de vídeo, imagen o MJPEG en
`sensores.json`; si el navegador no puede reproducirla, la cámara indica «Sin señal de vídeo».
Una carpeta `datos-locales/` creada antes conserva las URL de Internet: hay que borrarla (o cambiar
las URL) para usar las copias locales.

**Simulador de terminal.** Escribe solo sensores, mediante `modify` y escritura atómica. La aplicación
genera las alertas y controla automáticamente los actuadores. Se recomienda una copia
de `data/`, usando la misma carpeta en `LUMINA_DATA_DIR` y `--datos`:

```bash
python scripts/simular_sensores.py --datos /tmp/lumina-sprint3-demo --escenario calor
python scripts/simular_sensores.py --datos /tmp/lumina-sprint3-demo --escenario critica
python scripts/simular_sensores.py --datos /tmp/lumina-sprint3-demo --escenario movimiento
python scripts/simular_sensores.py --datos /tmp/lumina-sprint3-demo --escenario normal
python scripts/simular_sensores.py --datos /tmp/lumina-sprint3-demo --escenario fallo
```

Cada escenario escribe una vez y termina. `calor` sitúa la temperatura a umbral + 1 °C;
`critica`, exactamente en la crítica; `normal`, a umbral − 1 °C y sin movimiento en almacén;
`fallo` pone los sensores de temperatura en error. Los escenarios releen la configuración
vigente y renuevan la hora. La simulación aleatoria anterior sigue disponible:

```bash
python scripts/simular_sensores.py --intervalo 3 --semilla 7 --movimiento --ciclos 10
```

Los datos iniciales mantienen el instante del Sprint 1 (14/10/2026, 14:30), una alerta
abierta en almacén y el ventilador manual. La vigencia está desactivada por defecto.
El [guion completo](docs/sprint-3.md) prepara una demostración repetible desde esos datos.

## Documentación y comprobación

- [Sprint 3: criterios literales, tareas, pruebas, decisiones y demostración](docs/sprint-3.md).
- [Sprint 2](docs/sprint-2.md) y [Sprint 1](docs/sprint-1.md), conservados.
- [Arquitectura MVC y ciclo de reglas](docs/arquitectura.md).
- [Clases UML](docs/uml-clases.md) y [esquemas JSON](docs/esquemas-json.md).
- [Capturas del Sprint 3](docs/capturas/sprint-3), [del Sprint 2](docs/capturas/sprint-2) y [del Sprint 1](docs/capturas).

Desde esta carpeta se comprueba con el entorno propio (`.venv`, con YOLO y NiceGUI 3.19) y con
el del Sprint 1 (NiceGUI 3.18, sin YOLO), sin modificarlo:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/mypy
.venv/bin/ruff check .
../lumina-sprint1/.venv/bin/python -m pytest -q -p no:cacheprovider
```

**Verificación final** tras la revisión del 25/11/2026: **439 tests superados** con YOLO real
(388 anteriores, 47 del análisis de imagen, 1 de regresión de NiceGUI 3.19 y 3 de la revisión:
tildes en las imágenes marcadas y diálogos abiertos al cerrar la página); con el entorno del
Sprint 1, 435 superados y 4 omitidos porque necesitan YOLO u OpenCV. mypy estricto sin errores en
79 ficheros; ruff sin incidencias. Los tests desactivan los datos en vivo y el análisis de imagen
salvo en las pruebas que los comprueban, que usan un detector de prueba.

Las pruebas trabajan con copias temporales de `data/`, `FixedClock` y la simulación de
usuarios de NiceGUI. Comprueban concurrencia, configuración vigente, histéresis, modo
manual, permisos, responsables y escrituras conformes a los esquemas. El contrato conserva
sus campos y añade, como opcionales, el análisis de las cámaras (`personas`, `analizada_en`,
`captura`), la imagen de las alertas (`captura`) y el tipo `persona_zona_restringida`; sus tablas
se regeneran con:

```bash
.venv/bin/python scripts/documentar_esquemas.py
```

La entrega se identifica como **Lumina Sprint 3**, con `es.lumina.sprint3`. El empaquetado
manual mediante `scripts/empaquetar.py` usa ese nombre y deja fuera YOLO, PyTorch y OpenCV (el
ejecutable pesaría cerca de 1 GB): en él, Supervisión indica que el análisis de imagen no está
disponible. El ejecutable de `dist/` es anterior a las ampliaciones del 04/11/2026 y del 18/11/2026:
hay que regenerarlo para incluirlas, y una carpeta de datos que ya existía
conserva sus cuentas y cámaras. `dist/Lumina Sprint 3.app` se regeneró
el 31/10/2026, ya con el bloqueo por intentos fallidos, y se comprobó en macOS: abre su ventana,
bloquea una cuenta tras tres contraseñas incorrectas, el administrador la desbloquea y al cerrar
la ventana no quedan sesiones abiertas.
En una instalación empaquetada, sus datos quedan separados de otras entregas:
`~/Library/Application Support/Lumina Sprint 3` en macOS, `%APPDATA%\Lumina Sprint 3`
en Windows o `~/.local/share/lumina-sprint-3` en Linux.

Los bloqueos por ruta coordinan los repositorios del mismo proceso. Un escritor externo
debe respetar el protocolo de escritura atómica; no hay transacciones entre procesos ni
entre varios ficheros. La maqueta física y la base de datos pertenecen a la fase 2.
