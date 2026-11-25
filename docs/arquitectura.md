# Arquitectura de Lumina (Sprints 1 a 3)

Lumina sigue el patrón **Modelo–Vista–Controlador** del anteproyecto (apartado 4.1.3): Python
para la lógica, NiceGUI para la interfaz y ficheros JSON como almacenamiento de la fase 1. Se
ejecuta como aplicación de escritorio: un servidor local (solo `127.0.0.1`) y una ventana propia.

## Diagrama de componentes

```mermaid
flowchart LR
    U(["Usuario<br/>gerente · seguridad · administrador · superadministrador"])
    subgraph V["Vista · lumina/views (NiceGUI)"]
        R["Router<br/>sesión y permiso por ruta"]
        P["Páginas<br/>Login · Registro · Dashboard · Usuarios · Mi perfil · Supervisión · Configuración"]
        K["Componentes<br/>menú, indicadores, cámaras, tablas, formularios"]
        L["LiveData<br/>revalidación y refresco periódico"]
    end
    subgraph C["Controlador · lumina/controllers (sin NiceGUI)"]
        A["AuthController<br/>login · bloqueo por intentos · registro · logout"]
        UC["UserController<br/>cuentas · roles · jerarquía · perfil"]
        FC["FacilityController · SupervisionController<br/>establecimiento, alertas y equipos"]
        FA["FacilityAnalyzer<br/>vigencia · contadores · ambiente · movimiento"]
        CFG["ConfigurationController<br/>validación y guardado"]
        RE["RulesController<br/>alertas y ventilación automática"]
        S["PasswordHasher · UserInputValidator"]
        LS["LiveSimulator<br/>lecturas en vivo"]
        VC["VisionController<br/>análisis de imagen: personas por cámara"]
        Y["YoloPersonDetector · VideoFrameReader<br/>YOLO (ultralytics) y OpenCV, cargados al usarse"]
    end
    subgraph M["Modelo · lumina/models + lumina/repositories"]
        E["Entidades<br/>User, Sensor, Camera, Actuator, Alert, Reading, SystemConfig"]
        I["Interfaces de repositorio"]
        J["Repositorios JSON<br/>validación, caché y escritura atómica"]
        CR["FileCaptureRepository<br/>imágenes marcadas"]
    end
    D[("data/*.json")]
    CP[("capturas/*.jpg")]
    X(["SensorSimulator<br/>scripts/simular_sensores.py"])
    U --> R --> P --> K
    P -- "acciones" --> A
    P -- "acciones" --> UC
    A --> S
    UC --> S
    A --> I
    UC --> I
    P --> L --> FC
    FC --> FA
    FC --> I
    P -- "guardar configuración" --> CFG
    CFG --> I
    CFG -- "tras guardar" --> RE
    RE --> FA
    RE --> I
    T["LuminaApp: un temporizador del servidor"] --> RE
    J -. "implementa" .-> I
    J --> E
    J <--> D
    X -- "modify: lectura estricta y escritura atómica" --> J
    LS -- "modify en cada refresco (BackgroundCycle)" --> I
    VC -- "fotograma y personas" --> Y
    VC -- "cameras.modify y captura (BackgroundCycle)" --> I
    CR -. "implementa" .-> I
    CR <--> CP
```

## Capas y reglas

| Capa | Carpeta | Responsabilidad | Regla |
| ---- | ------- | --------------- | ----- |
| Modelo | `lumina/models` | Entidades inmutables, enumerados y variables calculadas (`UserCounts`, `FacilityStatus`, `SupervisionSnapshot`…) | Sin dependencias de E/S |
| Modelo | `lumina/repositories` | Contratos de lectura/escritura (`interfaces.py`) y su implementación JSON | Solo aquí se tocan ficheros |
| Controlador | `lumina/controllers` | Acceso, usuarios, supervisión, configuración y reglas | No importa NiceGUI: se prueba sin interfaz |
| Vista | `lumina/views` | Pantallas (una clase por pantalla), componentes y tema visual | No lee ficheros; solo Python (sin JavaScript, CSS ni HTML a mano) |
| Arranque | `main.py`, `lumina/launcher.py`, `lumina/app.py` | Prepara el proceso, une las tres capas, programa la simulación en vivo y el análisis de imagen (`BackgroundCycle`) y abre la ventana | — |

Las reglas se comprueban automáticamente: `mypy --strict` (tipos), `tests/test_project_rules.py`
(nada de JavaScript, Vue ni CSS en la interfaz) y `tests/test_desktop.py` (el lanzador no carga NiceGUI).

## Cómo se comunican la vista, la lógica y el almacenamiento

1. **Rutas.** `Router` registra cada pantalla en NiceGUI. En cada visita comprueba la sesión
   (el `id` del usuario en `app.storage.user`) y el permiso del rol; si no procede, redirige al
   inicio de sesión o al dashboard sin llegar a construir la página.
2. **Acciones.** Un botón llama a un método del controlador a través de `ProtectedPage.act()` o
   `act_async()` (acciones que evalúan reglas, ejecutadas en un hilo). Ambas variantes
   vuelven a leer la sesión y el permiso en ese momento y muestran el resultado (o el error de
   negocio) como notificación. Así, quitar el permiso a alguien surte efecto en las páginas que ya
   tenía abiertas. `act_async()` muestra el aviso y relee los datos (`then=`) en la página y no en
   el botón pulsado, que un refresco ha podido borrar mientras se esperaba al hilo.
3. **Lógica.** El controlador valida los datos, aplica las reglas y usa los repositorios por su
   interfaz (`UserRepository`…), nunca los ficheros.
4. **Datos.** El repositorio JSON traduce entre entidades y JSON (claves en español), valida tipos
   con mensajes que indican fichero, posición y campo, y guarda de forma atómica.
5. **Refresco.** Las pantallas con datos cambiantes usan `LiveData`, que los relee cada
   `LUMINA_REFRESH_SECONDS` y redibuja si cambian los datos o el día actual del reloj.
   Cada consulta revalida la sesión y el permiso; una cuenta desactivada vuelve al login y un
   perfil sin permiso de supervisión vuelve al dashboard, sin consultar de nuevo el lector y
   desactivando su temporizador. También se recalcula la vigencia aunque el fichero no haya
   cambiado. Si falla la primera lectura, `value` es `None`, se avisa y se sigue reintentando;
   los bloques independientes del dashboard siguen visibles. Tras una lectura válida se
   conserva ese valor durante fallos posteriores. Un intervalo de cero desactiva el refresco periódico.

### Sensores y refresco (H2.1–H2.4)

```mermaid
sequenceDiagram
    participant Sim as LiveSimulator / SensorSimulator
    participant Repo as Repositorios JSON
    participant JSON as sensores.json
    participant Live as LiveData
    participant Page as DashboardPage / SupervisionPage
    participant Ctrl as FacilityController / SupervisionController
    Sim->>Repo: modify(id, generar desde la lectura vigente)
    Repo->>JSON: lectura estricta + temporal + renombrado
    Note over Repo,JSON: Cada sensor tiene su propia transacción.<br/>Se conservan las cámaras y los demás sensores.
    Live->>Page: current_user(): revalidar sesión y permiso
    Live->>Ctrl: status() / snapshot()
    Ctrl->>Repo: cargar configuración, sensores y cámaras
    Repo->>JSON: releer si cambia fecha o tamaño
    Ctrl->>Ctrl: FacilityAnalyzer calcula estado y agregados
    Ctrl-->>Live: dataclasses inmutables comparables
    Live->>Page: refrescar si cambian los datos o el día
```

`FacilityController.status` alimenta aforo, plazas y ambiente de todos los dashboards.
`SupervisionController.snapshot` alimenta cámaras, movimiento por zona, lecturas, alertas y equipos. `FacilityAnalyzer` concentra las reglas puras. `SensorState` distingue el estado
efectivo de presentación del `SensorStatus` persistido: «Sin datos» no añade un valor al esquema.
Los valores NaN y ±infinito son errores de datos del sensor: se clasifican como «Error», se
excluyen de los agregados y detecciones y se presentan como «Lectura inválida» con su unidad.

La zona ambiental se obtiene de `zona_principal`; se muestran medias solo de sus sensores
operativos, con la hora más antigua de los contribuyentes. Los contadores operativos se suman,
se redondean a personas/plazas enteras y se acotan entre cero y capacidad, conservando en la
lista de sensores la lectura original. Sin contadores operativos el agregado es cero y su hora
es desconocida. Las zonas sin sensor de movimiento operativo muestran su indisponibilidad,
nunca una ausencia de movimiento inventada. Las reglas y sus prioridades están en
[sprint-2.md](sprint-2.md#decisiones-de-implementación).

`SensorSimulator` escribe sensores; la aplicación los consulta y genera alertas o modifica
equipos mediante `RulesController`. El simulador conserva el modo aleatorio y añade
escenarios deterministas de calor, crítica, movimiento, normalidad y fallo. No escribe
históricos.

**Datos en vivo.** Mientras no haya maqueta física, la propia aplicación hace de sensores:
`LuminaApp` programa un `BackgroundCycle` que, cada `LUMINA_REFRESH_SECONDS`, ejecuta
`LiveSimulator.step()` en un hilo (sin bloquear la interfaz, sin solaparse y esperando el ciclo
en curso al cerrar). Cada sensor operativo recibe una lectura nueva y verosímil mediante
`modify`: temperatura y humedad oscilan alrededor de su valor habitual con un ciclo diario suave,
aforo y parking siguen la afluencia de cada hora sin salir de [0, capacidad], la distancia del
acceso baja al pasar un coche y el movimiento aparece de forma breve y esporádica. Todas las
lecturas renuevan su hora, así que las pantallas nunca muestran siempre el mismo dato. Las reglas
evalúan esas lecturas igual que las de la maqueta: una detección simulada en una zona restringida
abre una alerta (una sola abierta por sensor) y enciende LED y alarma de su zona. No inventa
lecturas ausentes ni repara sensores en error o desactualizados, y si otra fuente escribe un
sensor (la maqueta, `SensorSimulator` y sus escenarios…) se lo deja durante dos minutos desde
su última escritura, de modo que los escenarios de demostración se comportan como antes.
`LUMINA_SIMULATION=false` la desactiva; los tests la desactivan por defecto.

**Cámaras.** `CameraTile` reproduce en bucle, sin sonido ni controles, el vídeo de la URL de la
cámara (`.mp4`, `.webm`…), con el rótulo «EN DIRECTO», la hora sobreimpresa que avanza cada
segundo y un aviso «Sin señal de vídeo» si el navegador no puede reproducirlo. Los datos de
ejemplo apuntan a grabaciones reales de videovigilancia de una tienda y de un aparcamiento
(dominio público, Wikimedia Commons), guardadas en `assets/camaras/` y servidas por la propia
aplicación desde el 18/11/2026. Una URL de imagen o MJPEG se muestra como imagen y, sin
URL, se mantiene la vista simulada o «Cámara sin conexión», con la detección de la zona aparte.
`SupervisionPage` construye las cámaras una sola vez y en cada refresco solo cambia sus rótulos,
de modo que el vídeo no se reinicia. No se añade captura de vídeo físico ni almacenamiento.

### Configuración, reglas y seguimiento (H3.1–H3.4)

```mermaid
sequenceDiagram
    participant Admin as ConfigurationPage
    participant Config as ConfigurationController
    participant App as LuminaApp (servidor)
    participant Rules as RulesController
    participant Repo as Repositories JSON
    participant View as LiveData / AlertWatcher
    Admin->>Config: act_async(): update(cambios, actor) en un hilo
    Config->>Repo: config.modify(validar y reautorizar)
    Repo-->>Config: configuración guardada atómicamente
    Config->>Rules: evaluate()
    loop Cada refresh_seconds (si es mayor que 0)
        App->>Rules: evaluate() en un hilo
        Rules->>Repo: configuración vigente estricta y sensores
        Rules->>Rules: calcular salud, temperatura por zona y condiciones
        Rules->>Repo: alerts.add(check=sin abierta del mismo tipo/zona/sensor)
        Rules->>Repo: actuators.modify(respetar manual, aplicar histéresis)
        Rules-->>App: RulesResult(alertas creadas, equipos cambiados)
    end
    View->>View: revalidar sesión y permiso
    View->>Repo: consultas mediante SupervisionController
    View->>View: refrescar estados, contador y aviso de alerta nueva
```

`LuminaApp.setup` crea un solo `app.timer` del servidor: abrir más páginas no crea más
motores. `refresh_seconds = 0` desactiva ese temporizador y los refrescos periódicos.
Guardar configuración o devolver un ventilador a automático evalúa las reglas también
con intervalo 0. Tanto el ciclo como esas acciones ejecutan el controlador en un hilo,
sin bloquear el bucle de eventos. Cualquier excepción del ciclo se anota en el diagnóstico
y permite el siguiente intento. Al cerrar se cancela el temporizador y se espera la
evaluación en curso antes de terminar; no se crea un registro de actividad de negocio.

El motor no importa NiceGUI y recibe `Clock`; las pruebas lo llaman directamente con
`FixedClock`. Temperatura ≥ crítica, movimiento operativo en zona restringida y sensor
en error (explícito o por lectura no finita) generan sus respectivos tipos de alerta. La deduplicación está dentro de
`add(check=...)`, bajo el cerrojo del fichero. Una alerta resuelta se conserva y permite
una nueva incidencia si sigue presente la condición.

La ventilación usa la máxima temperatura operativa de la zona. Se enciende por encima
del umbral y se apaga a umbral − 0,5 °C o menos. En la banda o sin lectura válida conserva
el estado. La acción manual fija `modo=manual`, aunque no cambie el encendido; las reglas
lo respetan. «Volver a automático» reactiva su evaluación inmediata. El movimiento
restringido enciende LED y alarma de esa zona en automático; no los apaga al desaparecer.

`SupervisionPage` contiene el listado completo de alertas con su detalle; no se añade
`/alertas`. Activa se persiste como `pendiente`, junto con `en_revision` y `resuelta`.
`update_alert` conserva los datos originales y guarda el nombre vigente del responsable
en `atendida_por` y el momento en `actualizada_en`. Repetir el mismo estado conserva
ambos; una resuelta no se reabre. Cada control revalida al actor dentro de `modify`
mediante una lectura estricta de la cuenta, sin escribirla.

`ConfigurationPage` solo admite administración (`CONFIGURE_SYSTEM`). Alertas y controles
exigen `MANAGE_ALERTS` / `CONTROL_ACTUATORS`. Gerencia consulta estados de equipos en el
dashboard, sin controles ni avisos. `AlertWatcher` revalida el permiso antes de consultar.
La configuración se confirma antes de evaluar reglas: son transacciones independientes;
si falla la evaluación posterior, se mantiene la configuración y el siguiente ciclo reintenta.
También se validan los umbrales al leer el JSON: finitos, entre −10 y 60 °C y crítica mayor
que umbral; un documento inválido impide evaluar reglas con esos valores. El formulario
solo se reconstruye automáticamente si no tiene ediciones pendientes, conservando también
lo escrito mientras termina un guardado. El contador de alertas admite un fallo inicial:
reintenta y establece su referencia en la primera lectura válida, sin anunciar las alertas
anteriores como nuevas ni impedir construir el resto de la página.

### Análisis de imagen con YOLO (ampliación del 18/11/2026)

```mermaid
sequenceDiagram
    participant App as LuminaApp (BackgroundCycle)
    participant Vision as VisionController
    participant Frames as VideoFrameReader (OpenCV)
    participant Yolo as YoloPersonDetector (ultralytics)
    participant Repo as Repositorios (sensores.json, capturas/)
    participant Rules as RulesController
    loop Cada refresh_seconds, en un hilo
        App->>Vision: step()
        Vision->>Yolo: prepare() (descarga yolo26n.pt la primera vez)
        loop Cada cámara activa con URL
            Vision->>Frames: read(cámara, ahora)
            Frames-->>Vision: fotograma (o None sin señal)
            Vision->>Yolo: detect(fotograma)
            Yolo-->>Vision: recuadros de personas
            Vision->>Repo: captures.save(imagen marcada) si hay personas
            Vision->>Repo: cameras.modify(personas, analizada_en, captura)
        end
        Vision->>Repo: borrar capturas antiguas que nadie usa
    end
    App->>Rules: evaluate() (su propio temporizador)
    Rules->>Repo: cámaras con personas en zonas restringidas
    Rules->>Repo: alerts.add(persona_zona_restringida, captura) y actuators.modify(LED y alarma)
```

El análisis de una cámara es una lectura más, guardada en la propia cámara: la regla lo trata como
el movimiento de su zona. `VisionController` no importa NiceGUI, YOLO ni OpenCV; recibe un
`PersonDetector` y un `FrameReader`, así que los tests usan otros de prueba y el detector se puede
sustituir (otro modelo, otra biblioteca o una cámara que ya detecte personas). `controllers/yolo.py`
es el único módulo que importa ultralytics y OpenCV, y lo hace la primera vez que se usan: sin ellos
(o en el ejecutable, que no los incluye) el estado del análisis es «No disponible» y el resto de la
aplicación funciona igual. Si otro programa escribe el análisis de una cámara, el ciclo se lo deja
dos minutos. Las imágenes se guardan con nombres únicos en `capturas/` (carpeta de datos), se
referencian desde los JSON con rutas relativas y se sirven en `/capturas`.

### Inicio de sesión (H1.2)

```mermaid
sequenceDiagram
    actor Usuario
    participant Login as LoginPage
    participant Auth as AuthController
    participant Repo as UserRepository (JSON)
    participant F as usuarios.json
    Usuario->>Login: correo y contraseña
    Login->>Auth: login(email, password)
    Auth->>Repo: find_by_email(email)
    Repo->>F: lectura (con caché por fecha de modificación)
    break cuenta bloqueada
        Auth-->>Login: AuthenticationError («pide al administrador que la desbloquee»)
    end
    Auth->>Auth: verificar hash PBKDF2
    break contraseña incorrecta
        Auth->>Repo: modify(id, sumar intento fallido)
        Note over Repo,F: al tercero seguido, bloqueado = true
        Repo->>F: escritura atómica
        Auth-->>Login: AuthenticationError (intentos restantes o bloqueo)
    end
    Auth->>Repo: modify(id, marcar conectado y poner el contador a cero)
    Note over Repo,F: bajo cerrojo: se comprueba que la cuenta sigue activa,<br/>con perfil y sin bloquear antes de guardar
    Repo->>F: escritura atómica (temporal + renombrado)
    Auth-->>Login: User con su rol
    Login->>Login: guarda la sesión (app.storage.user)
    Login-->>Usuario: dashboard de su perfil
```

Tras `MAX_FAILED_ATTEMPTS` (3) contraseñas incorrectas seguidas la cuenta queda bloqueada en
`usuarios.json`; la desbloquea desde «Usuarios» (`UserController.unlock`) un administrador o, si
es una cuenta de administración, el superadministrador.

### Edición de una cuenta por el administrador (H1.3)

```mermaid
sequenceDiagram
    actor Admin as Administrador
    participant Page as UsersPage
    participant UC as UserController
    participant Repo as UserRepository (JSON)
    Admin->>Page: Editar · Guardar cambios
    Page->>Page: act(): relee sesión y permiso
    Page->>UC: update_account(id, nombre, correo, actor)
    UC->>UC: normaliza y valida nombre y correo
    UC->>Repo: modify(id, cambio)
    Note over UC,Repo: en la misma transacción: el actor sigue teniendo el permiso,<br/>puede gestionar la cuenta vigente (jerarquía) y el correo no está ocupado
    Repo-->>UC: cuenta actualizada
    UC-->>Page: User
    Page-->>Admin: «Datos del usuario actualizados.»
```

## Control de acceso por roles

Los permisos salen de los casos de uso del anteproyecto (`lumina/models/enums.py`):

| Permiso | Gerente | Seguridad | Administrador | Superadministrador | Sprint |
| ------- | :-----: | :-------: | :-----------: | :----------------: | :----: |
| `gestionar_usuarios` (cuentas, roles, solicitudes, desbloqueos) | | | ✓ | ✓ | 1 |
| `gestionar_administradores` (perfil, datos, activación y desbloqueo de administradores) | | | | ✓ | 2 |
| `ver_establecimiento` (aforo, parking, clima) | ✓ | ✓ | ✓ | ✓ | 2 |
| `supervisar` (sensores y cámaras) | | ✓ | ✓ | ✓ | 2 |
| `gestionar_alertas` | | ✓ | ✓ | ✓ | 3 |
| `controlar_actuadores` | | ✓ | ✓ | ✓ | 3 |
| `configurar_sistema` (umbrales y zonas) | | | ✓ | ✓ | 3 |
| `ver_historicos` (históricos y estadísticas) | ✓ | ✓ | ✓ | ✓ | 4 |
| `ver_registros` (conectados y actividad) | | | ✓ | ✓ | 4 |

**Jerarquía de cuentas.** Superadministrador > administrador > seguridad y gerencia. Una cuenta
con `gestionar_usuarios` solo modifica cuentas de rango inferior al suyo y solo asigna perfiles
inferiores (`Role.can_manage`, `User.can_manage`). Por eso **los administradores no se pueden
modificar entre sí** ni dar de alta o ascender administradores: el superadministrador es quien
gestiona sus perfiles y permisos, sus datos, su activación («cerrar la cuenta») y su desbloqueo.
El perfil `superadmin` no lo asigna ni lo modifica nadie desde la aplicación. `UserController`
lo comprueba con las versiones vigentes de las dos cuentas dentro de la transacción que guarda
el cambio, y «Usuarios» solo ofrece controles en las filas que quien mira puede gestionar.

«Mi perfil» está disponible para todos. El acceso se comprueba en tres sitios: el **menú** solo
muestra lo permitido, el **router** rechaza la ruta y el **controlador** vuelve a comprobar el
permiso del actor en las acciones de escritura (en la misma transacción que guarda el cambio).
Las consultas de supervisión se protegen mediante
`SupervisionPage.permission = Permission.SUPERVISE`, tanto al entrar como en cada `LiveData`.

Otras medidas: contraseñas con PBKDF2-SHA256 y sal aleatoria (nunca en claro); una solicitud sin
perfil y una cuenta desactivada no pueden entrar; tres contraseñas incorrectas seguidas bloquean la
cuenta hasta que la desbloquea quien puede gestionarla; la sesión dura lo que la ventana (clave
aleatoria por ejecución) y al cerrarla la cuenta queda desconectada.

## Persistencia en JSON

- **Lectura con caché**: un fichero solo se vuelve a leer si cambia su fecha o su tamaño.
- **Tolerancia**: si otro proceso deja un JSON a medias, la interfaz sigue mostrando la última
  versión válida durante unos segundos; las **escrituras**, en cambio, exigen la versión actual.
- **Escritura atómica**: fichero temporal en la misma carpeta y renombrado.
- **Transacciones**: `Repository.modify()` lee, cambia y guarda bajo un mismo cerrojo; `add()`
  admite una comprobación (`check`) dentro de esa transacción. `ConfigRepository.modify()`
  agrupa el cambio del documento de configuración. Los JSON con la misma ruta comparten
  cerrojo dentro del proceso, aunque se creen repositorios distintos. No hay bloqueo entre
  procesos externos ni una transacción conjunta de varios ficheros.
- **Imágenes**: las del análisis de imagen se guardan aparte, en `capturas/` (`CaptureRepository`),
  con escritura atómica; los JSON solo guardan su referencia.
- **Contrato**: `schemas/*.schema.json` describe cada fichero (ver [esquemas-json.md](esquemas-json.md)).
  `scripts/documentar_esquemas.py` regenera sus tablas con la biblioteca estándar y
  `tests/test_schema_documentation.py` comprueba que el documento esté al día.
- **Una sola instancia** por carpeta de datos (bloqueo del sistema sobre `data/.lumina.lock`).

## Aplicación de escritorio

`main.py` → `Launcher` (registro de diagnóstico en el ejecutable, bloqueo de instancia, sesiones de
la ventana, datos iniciales) → `LuminaApp` (une Modelo, Controlador y Vista) → NiceGUI en modo
nativo: servidor en `127.0.0.1` y ventana con pywebview. `scripts/empaquetar.py` lo convierte en
ejecutable con PyInstaller, sin YOLO, PyTorch ni OpenCV.

## Cómo crece en los siguientes sprints

- **Sprint 4**: históricos, estadísticas, registros y validación final. No se añaden a esta entrega.
- **Fase 2 (base de datos)**: basta con implementar las interfaces de `repositories/interfaces.py`
  (p. ej. `SqlUserRepository`) y pasar otro `Repositories` a `Services.create()`; controladores y
  vistas no cambian.
