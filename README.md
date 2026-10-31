# Lumina · Sprint 1

Entrega del **Sprint 1 (19 de octubre – 1 de noviembre de 2026)** de Lumina, la plataforma de
supervisión IoT de un supermercado y su parking (Proyecto de Ingeniería Informática 1 ·
Universidad Europea · 2026-27). Solo contiene el alcance de este sprint:

| Historia | Contenido | Dónde |
| -------- | --------- | ----- |
| H1.1 Arquitectura MVC y esquemas JSON | Modelo de datos, contratos de lectura/escritura y esquemas de usuarios, sensores, actuadores, alertas e históricos | `lumina/models`, `lumina/repositories`, `schemas/`, `docs/esquemas-json.md` |
| H1.2 Registro, login y cierre de sesión | Solicitud de cuenta, validación de credenciales, **bloqueo tras 3 contraseñas incorrectas seguidas**, dashboard según el rol, cierre de sesión | `views/pages/auth.py`, `views/pages/dashboard.py`, `controllers/auth.py` |
| H1.3 Administración de usuarios y roles | Listado, alta, **edición**, desactivación, **desbloqueo** y asignación de perfil (solo administración) | `views/pages/users.py`, `controllers/users.py` |
| H1.4 Mi perfil | Consulta y cambio de nombre, correo y contraseña de la propia cuenta | `views/pages/profile.py` |

La supervisión, las alertas, los actuadores, los históricos, la configuración y los registros
de actividad llegan en los Sprints 2 a 4; el dashboard indica en qué sprint aparece cada función.

![Dashboard de administración](docs/capturas/03-dashboard-administracion.png)

## Puesta en marcha

```bash
python3.13 -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py                                         # abre la ventana de Lumina
```

Cuentas de demostración: `ana.lopez@lumina.es` / `admin123` (Administrador),
`carlos.ruiz@lumina.es` / `seguridad123` (Seguridad), `marta.garcia@lumina.es` / `gerente123` (Gerente).
Para usarla en el navegador: `LUMINA_NATIVE=false python main.py`.

## Demostración del sprint

1. Solicitar una cuenta en «Registrarse»: queda pendiente de aprobación.
2. Entrar con credenciales válidas (y ver el error con unas inválidas, que indica los intentos restantes).
3. Cada perfil abre su propio dashboard con sus funciones.
4. Como administrador: aprobar la solicitud asignando un perfil, crear, editar y desactivar cuentas.
5. Bloquear una cuenta que no sea la de Ana con tres contraseñas incorrectas seguidas: ya no entra ni con
   la correcta. El administrador la ve «Bloqueada» en «Usuarios» y la desbloquea.
6. Con otro usuario: modificar nombre, correo o contraseña en «Mi perfil».
7. Cerrar sesión y comprobar que las pantallas protegidas ya no son accesibles.

Si se bloquea la única cuenta de administración, se recupera editando `usuarios.json` en la carpeta
de datos (`data/` o la del ejecutable): `"bloqueado": false` e `"intentos_fallidos": 0` en esa cuenta.

Documentación de la entrega:

- [Sprint 1: criterios, tareas, pruebas y guion de demostración](docs/sprint-1.md).
- [Arquitectura MVC](docs/arquitectura.md).
- [Diagramas de clases UML del código](docs/uml-clases.md).
- [Esquemas JSON y campos documentados](docs/esquemas-json.md).
- [Capturas de todas las pantallas](docs/capturas).

## Calidad

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/mypy
.venv/bin/ruff check .
```

Python 3.13, tipado estricto y pruebas de datos, esquemas, controladores, interfaz, escritorio
y reglas del proyecto. Las pruebas de interfaz usan la simulación de NiceGUI sin abrir ventanas.

## Ejecutable

`python scripts/empaquetar.py` crea `dist/Lumina Sprint 1.app` (macOS) o la carpeta del programa
en `dist/` (Windows, generándolo en Windows). Sus datos se guardan aparte de los de otras versiones,
en `~/Library/Application Support/Lumina Sprint 1` (macOS) o `%APPDATA%\Lumina Sprint 1` (Windows).

`dist/Lumina Sprint 1.app` se regeneró el 31/10/2026, ya con el bloqueo por intentos fallidos, y se
comprobó en macOS: abre su ventana, bloquea una cuenta tras tres contraseñas incorrectas, el
administrador la desbloquea y al cerrar la ventana no quedan sesiones abiertas.
