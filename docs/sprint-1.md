# Entrega del Sprint 1 de Lumina

Proyecto de Ingeniería Informática 1 · Universidad Europea · curso 2026-27.
**Fechas:** del 19 de octubre al 1 de noviembre de 2026, ambos incluidos.
**Planificación:** cuatro historias y 26 horas (6 + 8 + 8 + 4).
**Ampliación del 29/10/2026:** bloqueo de la cuenta tras tres contraseñas incorrectas seguidas y
desbloqueo manual por el administrador, dentro de H1.2 y H1.3
(ver [Bloqueo por intentos fallidos](#bloqueo-por-intentos-fallidos)).

El objetivo es disponer de la base MVC y del contrato de datos JSON de Lumina, y demostrar
el ciclo de acceso completo en la aplicación de escritorio: solicitar una cuenta, asignarle
un rol, iniciar sesión en el panel correspondiente, bloquear una cuenta tras tres contraseñas
incorrectas y desbloquearla desde la administración, administrar cuentas, editar el perfil
propio y cerrar la sesión. Los datos de sensores, actuadores, alertas e históricos definen
el contrato de H1.1; su existencia no supone haber entregado las funciones de los siguientes sprints.

## Trazabilidad con el Product Backlog

Los criterios entre comillas se reproducen literalmente. Los nombres de las pruebas corresponden
a funciones existentes; las pruebas parametrizadas cubren varios casos bajo el mismo nombre.

| Historia | Responsable | Horas | Criterio de aceptación literal | Dónde está implementado | Tests que lo prueban |
| --- | --- | ---: | --- | --- | --- |
| **H1.1 · Arquitectura MVC y esquemas JSON** | Alejandro Majado | 6 | «Existe un diagrama de arquitectura y esquemas de usuarios, sensores, actuadores, alertas e históricos con campos documentados.» | [docs/arquitectura.md](arquitectura.md), [docs/uml-clases.md](uml-clases.md), [docs/esquemas-json.md](esquemas-json.md); [lumina/models/entities.py](../lumina/models/entities.py), [lumina/models/enums.py](../lumina/models/enums.py), [lumina/repositories/interfaces.py](../lumina/repositories/interfaces.py), [lumina/repositories/json_repositories.py](../lumina/repositories/json_repositories.py); [schemas/usuarios.schema.json](../schemas/usuarios.schema.json), [schemas/sensores.schema.json](../schemas/sensores.schema.json), [schemas/actuadores.schema.json](../schemas/actuadores.schema.json), [schemas/alertas.schema.json](../schemas/alertas.schema.json), [schemas/historicos.schema.json](../schemas/historicos.schema.json). | En [tests/test_schemas.py](../tests/test_schemas.py): `test_every_data_file_has_its_schema`, `test_sample_data_follows_its_schema`, `test_every_field_is_documented`, `test_schemas_reject_invalid_data`, `test_identifiers_and_zones_are_consistent`, `test_what_the_application_writes_follows_the_schemas`, `test_every_repository_writes_what_its_schema_describes`. En [tests/test_json_store.py](../tests/test_json_store.py): `test_sample_data_loads`, `test_record_errors_point_to_the_field`, `test_writes_keep_other_keys`, `test_changes_are_not_saved_over_a_half_written_file`. Los diagramas se contrastan con el código mediante revisión documental. |
| **H1.2 · Registro, login y cierre de sesión · RF-01** | Víctor Rodríguez | 8 | «Las credenciales válidas abren el panel correcto; las inválidas dan error; una nueva solicitud queda pendiente de asignación por el administrador.» | [lumina/controllers/auth.py](../lumina/controllers/auth.py), [lumina/controllers/security.py](../lumina/controllers/security.py), [lumina/views/pages/auth.py](../lumina/views/pages/auth.py), [lumina/views/pages/dashboard.py](../lumina/views/pages/dashboard.py), [lumina/views/session.py](../lumina/views/session.py), [lumina/views/router.py](../lumina/views/router.py), [lumina/views/components/shell.py](../lumina/views/components/shell.py). | En [tests/test_controllers.py](../tests/test_controllers.py): `test_valid_credentials_sign_in_with_the_users_role`, `test_invalid_credentials_are_rejected`, `test_a_new_request_waits_for_the_administrator`, `test_registration_validation`, `test_logout_marks_the_user_as_disconnected`, `test_an_account_deactivated_while_logging_in_stays_deactivated`, `test_two_registrations_cannot_share_an_email`, `test_un_hash_danado_rechaza_el_login_sin_excepcion`. En [tests/test_ui.py](../tests/test_ui.py): `test_each_role_opens_its_own_dashboard`, `test_wrong_password_shows_an_error`, `test_a_new_request_is_approved_by_the_administrator`, `test_protected_pages_require_a_session`, `test_logout_closes_access_to_protected_pages`, `test_closing_the_window_ends_the_session`, `test_logging_out_always_ends_the_session`. |
| **H1.3 · Administración de usuarios y roles · RF-02** | Laura Poveda | 8 | «El administrador puede crear, editar, desactivar y asignar roles; usuarios no administradores no tienen acceso a esa gestión.» | [lumina/controllers/users.py](../lumina/controllers/users.py), [lumina/models/enums.py](../lumina/models/enums.py), [lumina/views/pages/users.py](../lumina/views/pages/users.py), [lumina/views/pages/base.py](../lumina/views/pages/base.py), [lumina/views/router.py](../lumina/views/router.py), [lumina/views/routes.py](../lumina/views/routes.py). | En [tests/test_controllers.py](../tests/test_controllers.py): `test_admin_creates_a_user_with_a_temporary_password`, `test_admin_edits_an_account`, `test_an_edited_account_cannot_take_another_email`, `test_admin_changes_roles_and_deactivates_accounts`, `test_only_admins_manage_users`, `test_admin_cannot_change_their_own_account_from_the_list`, `test_a_demoted_admin_cannot_keep_editing`, `test_an_admin_demoted_while_creating_a_user_cannot_finish`, `test_a_role_change_keeps_a_concurrent_login`. En [tests/test_ui.py](../tests/test_ui.py): `test_admin_creates_an_account`, `test_admin_edits_an_account`, `test_admin_deactivates_an_account`, `test_users_without_permission_cannot_manage_accounts`, `test_a_demoted_admin_loses_user_management`, `test_a_demoted_admin_dashboard_is_rebuilt`, `test_una_solicitud_desactivada_muestra_su_estado_real`. |
| **H1.4 · Mi perfil · RF-03** | Laura Poveda | 4 | «El usuario visualiza su información; cambios válidos se guardan y los datos de terceros no pueden modificarse.» | [lumina/controllers/users.py](../lumina/controllers/users.py) (`update_profile`, `change_password`), [lumina/views/pages/profile.py](../lumina/views/pages/profile.py), [lumina/views/pages/base.py](../lumina/views/pages/base.py), [lumina/views/components/shell.py](../lumina/views/components/shell.py). El identificador de la cuenta se obtiene de la sesión; el controlador exige la misma titularidad y comprueba el acceso dentro de `modify`. | En [tests/test_controllers.py](../tests/test_controllers.py): `test_user_updates_their_profile`, `test_user_changes_their_password`, `test_a_password_changed_meanwhile_is_not_overwritten`, `test_a_deactivated_account_cannot_finish_changing_its_password`, `test_mi_perfil_rechaza_modificar_datos_de_terceros`, `test_el_perfil_revalida_el_acceso_dentro_de_la_transaccion`. En [tests/test_ui.py](../tests/test_ui.py): `test_profile_changes_only_the_own_account`, `test_profile_changes_the_password`, `test_a_deactivated_account_loses_its_open_pages`, `test_saving_the_profile_with_unreadable_accounts_shows_an_error`, `test_el_perfil_refresca_datos_externos_sin_borrar_la_edicion`. |

La recuperación de errores y los permisos de las páginas abiertas se comprueban además con
`test_los_errores_de_escritura_se_muestran_y_no_guardan`,
`test_un_error_de_lectura_avisa_y_permite_recuperarse` y
`test_la_desactivacion_expulsa_sin_necesidad_de_pulsar_un_boton`, en
[tests/test_ui.py](../tests/test_ui.py). Son regresiones del alcance del Sprint 1.

### Bloqueo por intentos fallidos

Ampliación de H1.2 y H1.3 añadida el 29/10/2026. No forma parte del texto literal del Product
Backlog, así que su criterio se redacta aparte y no sustituye a los anteriores:

| Ampliación | Criterio de aceptación | Dónde está implementado | Tests que lo prueban |
| --- | --- | --- | --- |
| Bloqueo tras tres contraseñas incorrectas (H1.2) | Cada contraseña incorrecta de una cuenta existente suma un intento; tras el primer y el segundo fallo se indica cuántos quedan y al tercero seguido la cuenta queda bloqueada: ni siquiera la contraseña correcta permite entrar. Un inicio de sesión correcto pone el contador a cero. | `AuthController.login` y `MAX_FAILED_ATTEMPTS` en [lumina/controllers/auth.py](../lumina/controllers/auth.py); `User.failed_attempts`, `locked`, `with_failed_attempt` y `signed_in` en [lumina/models/entities.py](../lumina/models/entities.py); campos `intentos_fallidos` y `bloqueado` en [lumina/repositories/json_repositories.py](../lumina/repositories/json_repositories.py) y [schemas/usuarios.schema.json](../schemas/usuarios.schema.json). | En [tests/test_controllers.py](../tests/test_controllers.py): `test_three_wrong_passwords_lock_the_account`, `test_a_correct_password_resets_the_failed_attempts`, `test_unknown_emails_do_not_count_attempts`, `test_a_locked_account_keeps_its_open_session`, `test_simultaneous_wrong_passwords_are_all_counted`, `test_an_account_locked_while_logging_in_cannot_enter`, `test_a_wrong_password_does_not_count_against_one_changed_meanwhile`. En [tests/test_ui.py](../tests/test_ui.py): `test_three_wrong_passwords_lock_the_account_until_an_admin_unlocks_it` y el caso `intento` de `test_los_errores_de_escritura_se_muestran_y_no_guardan`. En [tests/test_schemas.py](../tests/test_schemas.py): `test_schemas_reject_invalid_data` y `test_what_the_application_writes_follows_the_schemas`. |
| Desbloqueo manual por el administrador (H1.3) | Solo un administrador puede desbloquear una cuenta, desde «Usuarios»; el desbloqueo pone el contador a cero y la cuenta vuelve a poder entrar. El panel de administración avisa de las cuentas bloqueadas. | `UserController.unlock` y `counts` en [lumina/controllers/users.py](../lumina/controllers/users.py); estado «Bloqueada», contador de intentos y botón «Desbloquear» en [lumina/views/pages/users.py](../lumina/views/pages/users.py); aviso en [lumina/views/pages/dashboard.py](../lumina/views/pages/dashboard.py). | En [tests/test_controllers.py](../tests/test_controllers.py): `test_only_an_administrator_unlocks_an_account`, `test_only_admins_manage_users`, `test_admin_cannot_change_their_own_account_from_the_list`, `test_account_counts`. En [tests/test_ui.py](../tests/test_ui.py): `test_three_wrong_passwords_lock_the_account_until_an_admin_unlocks_it` y el caso `desbloquear` de `test_los_errores_de_escritura_se_muestran_y_no_guardan`. |

Decisiones:

- **Qué se cuenta.** Solo las contraseñas incorrectas de cuentas existentes, incluidas las
  pendientes y las desactivadas. Un correo inexistente responde «Correo o contraseña incorrectos.»
  sin contar nada, y los intentos sobre una cuenta ya bloqueada no la modifican. El contador se
  guarda en `usuarios.json`, de modo que cerrar la aplicación no lo reinicia.
- **Transacción.** El intento se suma con `modify` sobre la versión actual de la cuenta: dos
  intentos simultáneos cuentan los dos, y un intento comprobado contra una contraseña que acaba
  de cambiar no se cuenta contra la nueva.
- **Sesiones abiertas.** El bloqueo impide iniciar sesiones nuevas, pero no expulsa a quien ya
  había entrado; si lo hiciera, cualquiera podría cerrar la sesión de otra persona escribiendo tres
  veces su correo. La desactivación sigue expulsando al momento.
- **Quién desbloquea.** Un administrador distinto del titular, porque la propia cuenta no se
  modifica desde la gestión de usuarios. Si se bloquea la única cuenta de administración, se
  recupera editando `usuarios.json` (`"bloqueado": false` e `"intentos_fallidos": 0`).
- **Mensajes.** Indicar cuántos intentos quedan deja ver que el correo existe; el registro de
  cuentas ya lo revela al rechazar un correo repetido, así que no se pierde ninguna protección.

## Tareas del anteproyecto

- [x] **1.1.1 · Diagrama de clases UML del proyecto.** Tres diagramas Mermaid en
  [uml-clases.md](uml-clases.md): modelo; repositorios y controladores; vista y arranque.
- [x] **1.1.2 · Definir las tablas/ficheros para usuarios, sensores, actuadores e incidencias.**
  Ficheros JSON de la fase 1 en [data/](../data/), contratos en [schemas/](../schemas/),
  documentación de cada campo en [esquemas-json.md](esquemas-json.md). Las incidencias se
  representan mediante `Alert` y `alertas.json`; sensores y cámaras comparten `sensores.json`.
  También se definen `historicos.json` y `configuracion.json` como contratos de datos.
- [x] **1.2.1 · Pantalla de login y registro.** `LoginPage` y `RegisterPage`, en
  [lumina/views/pages/auth.py](../lumina/views/pages/auth.py).
- [x] **1.2.2 · Validación de credenciales y redirección según el rol.** `AuthController.login`,
  `UserSession` y `Router`; `/dashboard` muestra el panel de la función del usuario mediante
  `DashboardPage`. Se utiliza una ruta común con contenido por rol, no tres rutas distintas.
  La validación cuenta además las contraseñas incorrectas seguidas y bloquea la cuenta a la tercera.
- [x] **1.3.1 · Tabla de usuarios del administrador.** `UsersPage`, con solicitudes pendientes
  primero y datos que se releen con `LiveData`.
- [x] **1.3.2 · Botones para crear/editar/desactivar usuarios y cambiar su rol.** Formulario de alta,
  diálogo de edición, botón de desactivación/reactivación, botón «Desbloquear» para las cuentas
  bloqueadas por intentos fallidos y selector de perfil en `UsersPage`.
  Aprobar una solicitud consiste en asignarle un rol. La propia cuenta se edita en «Mi perfil».
- [x] **1.4.1 · Ventana Mi perfil.** `ProfilePage`, en
  [lumina/views/pages/profile.py](../lumina/views/pages/profile.py), dentro de la ventana nativa.
- [x] **1.4.2 · Guardar cambios de nombre, correo o contraseña.** `UserController.update_profile`
  y `change_password`; normalización de nombre y correo, unicidad del correo, confirmación de
  contraseña y comprobación de la contraseña actual.

**Ignacio Torres no tiene una historia asignada en el Sprint 1.** El apoyo con datos JSON de ejemplo
y validación de los esquemas IoT es una propuesta de colaboración, no una asignación formal del
Excel ni una quinta historia. No se le atribuyen horas dentro de las 26 horas planificadas.

## Guion de demostración en siete pasos

Preparar una copia de los datos de ejemplo para poder repetir la demostración sin alterar
la entrega. Las tres cuentas iniciales son:

| Perfil | Correo | Contraseña |
| --- | --- | --- |
| Administrador | `ana.lopez@lumina.es` | `admin123` |
| Seguridad | `carlos.ruiz@lumina.es` | `seguridad123` |
| Gerente | `marta.garcia@lumina.es` | `gerente123` |

1. **Solicitar una cuenta.** Desde «Registrarse», introducir `Lucía Fernández`,
   `lucia.demo@lumina.es` y `secreta1` en ambos campos de contraseña. Mostrar la confirmación;
   intentar entrar con esa cuenta y comprobar el mensaje de solicitud pendiente.
2. **Validar el acceso de administración.** Entrar primero con `ana.lopez@lumina.es` y una
   contraseña incorrecta para mostrar el error, que indica los dos intentos que quedan antes del
   bloqueo. Repetir con `admin123`: el acierto pone el contador a cero, se abre
   «Dashboard · Administración» y se muestra la solicitud pendiente.
3. **Administrar las cuentas.** Abrir «Usuarios», asignar «Gerente» a Lucía, crear otra cuenta y
   mostrar su contraseña temporal. Editar el nombre/correo de esa cuenta y desactivarla;
   comprobar que la tabla refleja los cambios. Utilizar cuentas distintas de Ana para estas acciones.
4. **Bloquear y desbloquear una cuenta.** Cerrar sesión y esperar a «Iniciar sesión». Entrar tres
   veces con `carlos.ruiz@lumina.es` y una contraseña incorrecta: tras el primer y el segundo fallo
   se indica cuántos intentos quedan, y tras el tercero la cuenta queda bloqueada; ni siquiera
   `seguridad123` permite entrar. Entrar como Ana: el dashboard avisa de «1 cuenta bloqueada por
   intentos fallidos» y en «Usuarios» Carlos aparece «Bloqueada», con «3 intentos fallidos».
   Pulsar «Desbloquear». No hacer esta prueba con Ana: es la única cuenta de administración y nadie
   podría desbloquearla desde la aplicación.
5. **Comprobar los otros paneles y los permisos.** Cerrar sesión y esperar a «Iniciar sesión».
   Entrar como Carlos (`carlos.ruiz@lumina.es` / `seguridad123`), ya desbloqueado: se abre
   «Dashboard · Seguridad».
   Salir, esperar y entrar como Marta (`marta.garcia@lumina.es` / `gerente123`): se abre
   «Dashboard · Gerente». Ninguno tiene el menú «Usuarios»; la petición directa a `/usuarios`
   también vuelve al dashboard. Esto último se verifica sin navegador con
   `test_users_without_permission_cannot_manage_accounts`. Las funciones futuras aparecen con su sprint.
6. **Editar el perfil propio.** Con Marta, abrir «Mi perfil» y mostrar sus datos. Guardar un nuevo
   nombre y correo; intentar un correo inválido y comprobar el error. Cambiar la contraseña
   indicando `gerente123` como contraseña actual y `nueva123` dos veces. Verificar que las demás
   cuentas permanecen intactas; cerrar sesión, esperar y volver a entrar con el correo actualizado
   y `nueva123`.
7. **Cerrar el ciclo.** Cerrar sesión y esperar a «Iniciar sesión». Una ruta protegida debe
   redirigir al login (prueba `test_logout_closes_access_to_protected_pages`). Entrar con la
   cuenta aprobada de Lucía para demostrar que la asignación del paso 3 permite acceder.
   Cerrar sesión y la ventana al terminar.

Las [trece capturas](capturas/) documentan acceso, registro, paneles por rol, gestión de
usuarios, alta, edición, perfil y el bloqueo por intentos fallidos (capturas 11 a 13: aviso de
cuenta bloqueada, tabla de usuarios y aviso del dashboard). La captura móvil ilustra la maquetación actual;
la validación completa de responsive sigue planificada para el Sprint 4. Este guion describe
la demostración; la auditoría automatizada se ejecuta sin abrir ventanas ni navegadores.

## Definición de hecho

- [x] Los cuatro criterios literales tienen implementación y pruebas identificadas en la tabla.
- [x] Tres contraseñas incorrectas seguidas bloquean la cuenta, incluso para la contraseña correcta;
  solo un administrador la desbloquea y el contador se conserva en `usuarios.json`.
- [x] Arquitectura MVC, UML del código y campos de los esquemas JSON documentados y enlazados
  desde [README.md](../README.md).
- [x] Pantallas y bloques reutilizables definidos como clases; interfaz escrita en Python;
  controladores sin NiceGUI y vistas sin acceso directo a ficheros.
- [x] Credenciales inválidas, cuentas pendientes y desactivadas se rechazan; las rutas y acciones
  protegidas revalidan sesión y permiso. El perfil propio comprueba la titularidad en el controlador.
- [x] Las modificaciones usan `modify` o `add(check=...)`, con lectura estricta y autorización
  dentro de la transacción cuando corresponde. Las escrituras JSON son atómicas.
- [x] Los datos cambiantes se releen mediante `LiveData` con `refresh_seconds`; un fallo de lectura
  se comunica y los refrescos pueden recuperarse. Los cambios externos del perfil respetan
  los campos que se estén editando.
- [x] Regresiones de permisos, validación, concurrencia y rutas de error de la interfaz cubiertas.
- [x] Python 3.13; verificación con pytest, mypy estricto y ruff sin errores.
  Los tests usan copias temporales de `data/`; los servicios de pruebas inyectan
  `FixedClock(2026-10-14 14:30)`. La simulación de NiceGUI no abre la ventana nativa.

Comandos de verificación desde la raíz del proyecto:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/mypy
.venv/bin/ruff check .
```

Resultado de la verificación: **189 tests superados**, mypy sin errores en 50 ficheros y ruff
sin incidencias, con Python 3.13.5 y NiceGUI 3.18.0. La auditoría añadió 24 casos a los 152
iniciales (176) y el bloqueo por intentos fallidos, otros 13.

## Auditoría y decisiones de alcance

- **Titularidad y acceso de Mi perfil.** `update_profile` y `change_password` exigen el actor;
  rechazan un identificador ajeno y verifican el acceso vigente dentro de `modify`.
- **Hashes dañados.** El login trata los errores de formato, sal, iteraciones y comparación
  como credenciales incorrectas, sin propagar excepciones al formulario.
- **Errores de disco.** Las acciones, la comprobación de sesión y los refrescos muestran los
  errores de E/S; un fallo de escritura conserva los datos y no anuncia éxito.
  Un fichero con codificación UTF-8 dañada se comunica como `DataFormatError`, con la misma
  tolerancia de lectura y bloqueo de escritura que un JSON incompleto; lo prueba
  `test_la_codificacion_invalida_se_trata_como_datos_danados` en
  [tests/test_json_store.py](../tests/test_json_store.py).
- **Páginas abiertas.** El perfil y todos los dashboards releen la cuenta para detectar cambios
  de acceso y actualizar sus datos. Antes los perfiles sin administración solo revalidaban al actuar
  o navegar. Los formularios conservan la edición local durante los refrescos.
- **Estado de solicitudes desactivadas.** La tabla muestra «Desactivada» aunque aún no se haya
  asignado un rol, para que la solicitud pendiente no oculte la desactivación.
- **Versión de Python.** Se ajustan el mínimo declarado y las herramientas a Python 3.13,
  conforme al enunciado. Los alias y genéricos adoptan la sintaxis correspondiente a esa versión.
- **Interpretación del anteproyecto.** «Incidencias» corresponde a las alertas del modelo;
  «ventana Mi perfil» es una pantalla de la misma aplicación de escritorio. No se añaden
  otras ventanas, tablas SQL ni funciones de sprints posteriores.

## Fuera de alcance

| Sprint | Funciones previstas que no se implementan como parte de esta entrega |
| --- | --- |
| **Sprint 2** | Supervisión de sensores y cámaras; consulta de aforo y parking; temperatura y humedad (clima). |
| **Sprint 3** | Configuración del establecimiento, alertas, actuadores y reglas automáticas. |
| **Sprint 4** | Históricos y estadísticas, registros de actividad, responsive y validación final. |

Los enumerados, repositorios, esquemas y ejemplos IoT existentes son la base de H1.1.
Los contadores de cuentas del dashboard de administración apoyan la gestión del Sprint 1;
no constituyen el módulo de registros de actividad del Sprint 4.
