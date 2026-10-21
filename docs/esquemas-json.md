# Esquemas de los ficheros JSON

Contrato de datos de Lumina (H1.1). Cada fichero de `data/` tiene un esquema formal en
`schemas/` (JSON Schema 2020-12) que **es la referencia**: este documento se genera a partir de
ellos y los tests (`tests/test_schemas.py`) comprueban que los datos de ejemplo y lo que escribe
la aplicación los cumplen.

- Las claves están en español porque son el contrato compartido con la parte IoT.
- Las fechas van en ISO 8601 y hora local (`2026-10-14T14:30:00`); con zona horaria se convierten.
- Un fichero se escribe siempre completo y de una vez (fichero temporal + renombrado), nunca a medias.
- Los identificadores (`id`) son únicos dentro de cada lista y las zonas se referencian por su `id`
  de `configuracion.json`.

| Fichero | Contenido | Se usa a partir de |
| ------- | --------- | ------------------ |
| `usuarios.json` | Cuentas, perfiles y solicitudes | **Sprint 1** (H1.2–H1.4) |
| `sensores.json` | Última lectura de cada sensor y cámaras | Sprint 2 (H2.1–H2.4) |
| `actuadores.json` | Estado de ventiladores, LED y alarma | Sprint 3 (H3.2, H3.3) |
| `alertas.json` | Alertas e incidencias | Sprint 3 (H3.2, H3.4) |
| `historicos.json` | Serie histórica de lecturas | Sprint 4 (H4.1) |
| `configuracion.json` | Aforo, plazas, umbrales y zonas | Sprint 3 (H3.1) |

## `usuarios.json`

Cuentas de acceso a Lumina (H1.2, H1.3, H1.4). Las contraseñas nunca se guardan en claro.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `usuarios` | lista de *usuario* | ✓ | Todas las cuentas, incluidas las solicitudes pendientes de aprobación. |

**usuario** · Cuenta de un usuario.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `id` | texto | ✓ | Identificador único de la cuenta (p. ej. «usr-ana»). |
| `nombre` | texto | ✓ | Nombre visible. (máx. 45 caracteres) |
| `email` | texto | ✓ | Correo de acceso. Único sin distinguir mayúsculas; se guarda en minúsculas. |
| `password_hash` | texto | ✓ | Hash PBKDF2-SHA256: pbkdf2_sha256$iteraciones$sal$hash (hexadecimal). Nunca la contraseña en claro. |
| `rol` | `admin` · `seguridad` · `gerente` · null |  | Perfil de acceso. null = solicitud de cuenta pendiente de que el administrador le asigne uno. |
| `activo` | booleano |  | false = cuenta desactivada: no puede iniciar sesión. (por defecto `true`) |
| `conectado` | booleano |  | Sesión abierta. Lo actualiza la aplicación al entrar y al salir. (por defecto `false`) |
| `creado_en` | fecha ISO 8601 · null |  | Momento del alta o de la solicitud. ISO 8601 en hora local (2026-10-14T14:30:00). |
| `ultimo_acceso` | fecha ISO 8601 · null |  | Último inicio de sesión. ISO 8601 en hora local (2026-10-14T14:30:00). |

## `sensores.json`

Última lectura de cada sensor y cámaras de vigilancia (Sprint 2: H2.1, H2.4). Los escriben el simulador o la maqueta IoT.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `sensores` | lista de *sensor* | ✓ | Sensores del establecimiento. |
| `camaras` | lista de *camara* |  | Cámaras de vigilancia. |

**sensor** · Sensor y su última lectura.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `id` | texto | ✓ | Identificador único del sensor (p. ej. «temp-tienda»). |
| `nombre` | texto | ✓ | Nombre visible. |
| `tipo` | `temperatura` · `humedad` · `movimiento` · `distancia` · `contador_personas` · `contador_vehiculos` | ✓ | Tipo de sensor; la unidad se deduce de él (°C, %, cm, personas, coches). |
| `zona` | texto | ✓ | Identificador de una zona de configuracion.json. |
| `valor` | número · booleano · null |  | Última lectura. En «movimiento», true/1 = detectado. null = sin lectura. |
| `estado` | `activo` · `error` · `desactualizado` |  | Estado del sensor. (por defecto `activo`) |
| `actualizado_en` | fecha ISO 8601 · null |  | Momento de la última lectura. ISO 8601 en hora local (2026-10-14T14:30:00). |

**camara** · Cámara de vigilancia.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `id` | texto | ✓ | Identificador único de la cámara. |
| `nombre` | texto | ✓ | Nombre visible. |
| `zona` | texto | ✓ | Identificador de una zona de configuracion.json. |
| `url` | texto · null |  | URL de una imagen o de un flujo MJPEG. null = se muestra un marcador. |
| `estado` | `activo` · `error` |  | Estado de la cámara. (por defecto `activo`) |

## `actuadores.json`

Estado de los actuadores (Sprint 3: H3.2, H3.3). La maqueta debe leer «encendido» para actuar.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `actuadores` | lista de *actuador* | ✓ | Ventiladores, LED de aviso y alarma digital. |

**actuador** · Actuador y su estado.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `id` | texto | ✓ | Identificador único del actuador. |
| `nombre` | texto | ✓ | Nombre visible. |
| `tipo` | `ventilador` · `led` · `alarma` | ✓ | Tipo de actuador. |
| `zona` | texto | ✓ | Identificador de una zona de configuracion.json. |
| `encendido` | booleano |  | Estado binario: true = encendido o activada. (por defecto `false`) |
| `modo` | `automatico` · `manual` |  | Quién decidió el estado: las reglas automáticas o un usuario. (por defecto `manual`) |
| `actualizado_en` | fecha ISO 8601 · null |  | Último cambio de estado. ISO 8601 en hora local (2026-10-14T14:30:00). |

## `alertas.json`

Alertas e incidencias (Sprint 3: H3.2, H3.4). Ciclo de vida: pendiente → en revisión → resuelta.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `alertas` | lista de *alerta* | ✓ | Alertas registradas. |

**alerta** · Incidencia detectada.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `id` | texto | ✓ | Identificador único de la alerta (p. ej. «alr-0002»). |
| `tipo` | `movimiento_zona_restringida` · `temperatura_critica` · `fallo_sensor` | ✓ | Situación que la generó. |
| `zona` | texto | ✓ | Identificador de una zona de configuracion.json. |
| `fecha_hora` | fecha ISO 8601 | ✓ | Momento en que se detectó. ISO 8601 en hora local (2026-10-14T14:30:00). |
| `estado` | `pendiente` · `en_revision` · `resuelta` |  | Estado de la incidencia. (por defecto `pendiente`) |
| `descripcion` | texto · null |  | Texto breve para el personal de seguridad. |
| `sensor` | texto · null |  | Identificador del sensor que la detectó. |
| `atendida_por` | texto · null |  | Nombre de quien la revisó o resolvió por última vez. |
| `actualizada_en` | fecha ISO 8601 · null |  | Último cambio de estado. ISO 8601 en hora local (2026-10-14T14:30:00). |

## `historicos.json`

Lecturas históricas para estadísticas (Sprint 4: H4.1).

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `lecturas` | lista de *lectura* | ✓ | Serie de lecturas de las variables consultables. |

**lectura** · Valor de una variable en un instante.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `variable` | `aforo` · `parking` · `temperatura` · `humedad` | ✓ | Variable medida. |
| `fecha_hora` | fecha ISO 8601 | ✓ | Momento de la lectura. ISO 8601 en hora local (2026-10-14T14:30:00). |
| `valor` | número | ✓ | Valor: personas, coches, °C o % según la variable. |
| `estado` | `activo` · `error` · `desactualizado` |  | Estado del sensor al tomar la lectura. (por defecto `activo`) |

## `configuracion.json`

Parámetros del establecimiento (se editarán en el Sprint 3: H3.1). Si falta un campo se usa su valor por defecto.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `establecimiento` | texto |  | Nombre del establecimiento. (por defecto `Supermercado Lumina`) |
| `aforo_maximo` | entero |  | Personas que caben en la tienda. (por defecto `150`; ≥ 0) |
| `plazas_parking` | entero |  | Plazas del aparcamiento. (por defecto `50`; ≥ 0) |
| `umbral_temperatura` | número |  | °C a partir de los que debe encenderse el ventilador. (por defecto `26.0`) |
| `temperatura_critica` | número |  | °C que generan un aviso al personal de seguridad. (por defecto `30.0`) |
| `antiguedad_maxima_lectura_min` | entero · null |  | Minutos tras los que una lectura se considera desactualizada; null o 0 = no se comprueba. (≥ 0) |
| `zona_principal` | texto |  | Zona cuya temperatura y humedad muestra el dashboard. (por defecto `tienda`) |
| `zonas` | lista de *zona* |  | Zonas supervisadas; sensores, cámaras, actuadores y alertas las referencian por su id. |

**zona** · Zona del establecimiento.

| Campo | Tipo | Oblig. | Descripción |
| ----- | ---- | :----: | ----------- |
| `id` | texto | ✓ | Identificador único de la zona (p. ej. «almacen»). |
| `nombre` | texto | ✓ | Nombre visible. |
| `restringida` | booleano |  | true = el movimiento en esta zona genera una alerta. (por defecto `false`) |

---

_Generado a partir de `schemas/`. Si cambia un esquema, hay que regenerarlo._
