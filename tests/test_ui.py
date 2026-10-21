"""Interfaz del Sprint 1 con el usuario simulado de NiceGUI (sin ventana ni navegador).

El fixture ``user`` ejecuta ``main.py`` con la configuración de ``conftest.py``, es decir,
sobre una copia temporal de ``data/``. Los tests siguen la demostración del sprint:
solicitar cuenta, entrar con cada perfil, administrar usuarios, editar el perfil y salir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from nicegui.testing import User, user_simulation

LOGIN_RETRIES = 40  # el hash PBKDF2 de las cuentas de ejemplo tarda unas décimas de segundo
MAIN_FILE = Path(__file__).resolve().parent.parent / 'main.py'


async def login(user: User, email: str, password: str) -> None:
    await user.open('/login')
    user.find(marker='login-email').type(email)
    user.find(marker='login-password').type(password)
    user.find('Entrar').click()


def accounts(data_dir: Path) -> dict[str, dict[str, Any]]:
    users = json.loads((data_dir / 'usuarios.json').read_text(encoding='utf-8'))['usuarios']
    return {item['id']: item for item in users}


def edit_user(data_dir: Path, user_id: str, **fields: object) -> None:
    """Cambia una cuenta en ``usuarios.json``, como si lo hiciera otro administrador."""
    path = data_dir / 'usuarios.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    for item in document['usuarios']:
        if item['id'] == user_id:
            item.update(fields)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')


# --- H1.2 · Acceso -----------------------------------------------------------------------------


async def test_root_redirects_to_login(user: User) -> None:
    await user.open('/')
    await user.should_see('Iniciar sesión')
    await user.should_see('Supervisión del supermercado y parking')


@pytest.mark.parametrize('route', ['/dashboard', '/usuarios', '/perfil'])
async def test_protected_pages_require_a_session(user: User, route: str) -> None:
    await user.open(route)
    await user.should_see('Iniciar sesión')


async def test_wrong_password_shows_an_error(user: User) -> None:
    await login(user, 'carlos.ruiz@lumina.es', 'incorrecta')
    await user.should_see('Correo o contraseña incorrectos.', retries=LOGIN_RETRIES)


@pytest.mark.parametrize(
    ('email', 'password', 'title', 'visible', 'hidden'),
    [
        (
            'ana.lopez@lumina.es', 'admin123', 'Dashboard · Administración',
            ['Solicitudes', 'Gestionar cuentas, perfiles y solicitudes', 'Configurar umbrales y zonas restringidas'],
            [],
        ),
        (
            'carlos.ruiz@lumina.es', 'seguridad123', 'Dashboard · Seguridad',
            ['Supervisar sensores y cámaras', 'Controlar ventiladores, LED y alarma', 'Sprint 2'],
            ['Usuarios', 'Gestionar cuentas, perfiles y solicitudes'],
        ),
        (
            'marta.garcia@lumina.es', 'gerente123', 'Dashboard · Gerente',
            ['Consultar aforo, parking, temperatura y humedad', 'Consultar históricos y estadísticas'],
            ['Usuarios', 'Supervisar sensores y cámaras', 'Controlar ventiladores, LED y alarma'],
        ),
    ],
    ids=['administrador', 'seguridad', 'gerente'],
)
async def test_each_role_opens_its_own_dashboard(
    user: User, email: str, password: str, title: str, visible: list[str], hidden: list[str]
) -> None:
    await login(user, email, password)
    await user.should_see(title, retries=LOGIN_RETRIES)
    for text in ['Tu cuenta', email, 'Consultar y modificar tu perfil', *visible]:
        await user.should_see(text)
    for text in hidden:
        await user.should_not_see(text)


async def test_users_without_permission_cannot_manage_accounts(user: User) -> None:
    await login(user, 'marta.garcia@lumina.es', 'gerente123')
    await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
    await user.open('/usuarios')  # aunque escriba la ruta, vuelve a su dashboard
    await user.should_see('Dashboard · Gerente')
    await user.should_not_see('Gestionar accesos y perfiles')


async def test_a_new_request_is_approved_by_the_administrator(user: User, data_dir: Path) -> None:
    await user.open('/registro')
    user.find(marker='register-name').type('Lucía Fernández')
    user.find(marker='register-email').type('lucia@lumina.es')
    user.find(marker='register-password').type('secreta1')
    user.find(marker='register-confirmation').type('secreta1')
    user.find('Solicitar cuenta').click()
    await user.should_see('Solicitud enviada', retries=LOGIN_RETRIES)
    request = next(item for item in accounts(data_dir).values() if item['email'] == 'lucia@lumina.es')
    assert request['rol'] is None

    await login(user, 'lucia@lumina.es', 'secreta1')
    await user.should_see('pendiente de aprobación', retries=LOGIN_RETRIES)

    await login(user, 'ana.lopez@lumina.es', 'admin123')
    await user.should_see('1 solicitud de cuenta pendiente', retries=LOGIN_RETRIES)
    await user.open('/usuarios')
    await user.should_see('Pendiente de aprobación')
    user.find(marker=f'role-{request["id"]}').click()
    user.find('Gerente').click()
    await user.should_see('Perfil actualizado.')
    assert accounts(data_dir)[request['id']]['rol'] == 'gerente'

    user.find('Cerrar sesión').click()
    await user.should_see('Iniciar sesión')  # que termine la navegación
    await login(user, 'lucia@lumina.es', 'secreta1')
    await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)


async def test_logout_closes_access_to_protected_pages(user: User, data_dir: Path) -> None:
    await login(user, 'marta.garcia@lumina.es', 'gerente123')
    await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
    assert accounts(data_dir)['usr-marta']['conectado']
    user.find('Cerrar sesión').click()
    await user.should_see('Iniciar sesión')
    assert not accounts(data_dir)['usr-marta']['conectado']
    await user.open('/perfil')
    await user.should_see('Iniciar sesión')


async def test_closing_the_window_ends_the_session(data_dir: Path) -> None:
    """Cerrar la ventana de escritorio detiene el servidor y cierra la sesión que estaba abierta."""
    async with user_simulation(main_file=MAIN_FILE) as user:
        await login(user, 'marta.garcia@lumina.es', 'gerente123')
        await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
        assert accounts(data_dir)['usr-marta']['conectado']
    assert not accounts(data_dir)['usr-marta']['conectado']


# --- H1.3 · Administración de cuentas ---------------------------------------------------------


async def admin_on_users_page(user: User) -> None:
    await login(user, 'ana.lopez@lumina.es', 'admin123')
    await user.should_see('Dashboard · Administración', retries=LOGIN_RETRIES)
    await user.open('/usuarios')
    await user.should_see('3 usuarios · 2 conectados')


async def test_admin_creates_an_account(user: User, data_dir: Path) -> None:
    await admin_on_users_page(user)
    user.find('Añadir usuario').click()
    user.find(marker='new-name').type('Pedro Gil')
    user.find(marker='new-email').type('pedro@lumina.es')
    user.find('Guardar usuario').click()
    await user.should_see('Usuario creado', retries=LOGIN_RETRIES)
    created = next(item for item in accounts(data_dir).values() if item['email'] == 'pedro@lumina.es')
    assert created['rol'] == 'gerente'


async def test_admin_edits_an_account(user: User, data_dir: Path) -> None:
    await admin_on_users_page(user)
    user.find(marker='edit-usr-marta').click()
    await user.should_see('Editar usuario')
    user.find(marker='edit-name').clear().type('Marta García Ruiz')
    user.find(marker='edit-email').clear().type('marta.garcia.ruiz@lumina.es')
    user.find(marker='edit-save').click()
    await user.should_see('Datos del usuario actualizados.')
    marta = accounts(data_dir)['usr-marta']
    assert (marta['nombre'], marta['email']) == ('Marta García Ruiz', 'marta.garcia.ruiz@lumina.es')


async def test_admin_deactivates_an_account(user: User, data_dir: Path) -> None:
    await admin_on_users_page(user)
    user.find(marker='active-usr-marta').click()
    await user.should_see('Cuenta desactivada.')
    assert accounts(data_dir)['usr-marta']['activo'] is False
    user.find('Cerrar sesión').click()
    await user.should_see('Iniciar sesión')  # que termine la navegación
    await login(user, 'marta.garcia@lumina.es', 'gerente123')
    await user.should_see('Tu cuenta está desactivada', retries=LOGIN_RETRIES)


async def test_a_demoted_admin_loses_user_management(user: User, data_dir: Path) -> None:
    await admin_on_users_page(user)
    edit_user(data_dir, 'usr-ana', rol='gerente')  # otro administrador le quita el perfil
    user.find(marker='active-usr-marta').click()
    await user.should_see('Dashboard · Gerente')
    assert accounts(data_dir)['usr-marta']['activo'] is True


async def test_a_demoted_admin_dashboard_is_rebuilt(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.2')  # con refrescos, como en la aplicación
    async with user_simulation(main_file=MAIN_FILE) as user:
        await login(user, 'ana.lopez@lumina.es', 'admin123')
        await user.should_see('Dashboard · Administración', retries=LOGIN_RETRIES)
        edit_user(data_dir, 'usr-ana', rol='gerente')
        await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
        await user.should_not_see('Solicitudes')


# --- H1.4 · Mi perfil --------------------------------------------------------------------------


async def test_profile_changes_only_the_own_account(user: User, data_dir: Path) -> None:
    before = accounts(data_dir)
    await login(user, 'marta.garcia@lumina.es', 'gerente123')
    await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
    await user.open('/perfil')
    await user.should_see('Datos personales')
    user.find(marker='profile-name').clear().type('Marta García López')
    user.find('Guardar cambios').click()
    await user.should_see('Datos actualizados.')
    after = accounts(data_dir)
    assert after['usr-marta']['nombre'] == 'Marta García López'
    others = ('usr-ana', 'usr-carlos')
    assert {key: after[key] for key in others} == {key: before[key] for key in others}  # nada de terceros


async def test_profile_changes_the_password(user: User) -> None:
    await login(user, 'carlos.ruiz@lumina.es', 'seguridad123')
    await user.should_see('Dashboard · Seguridad', retries=LOGIN_RETRIES)
    await user.open('/perfil')
    user.find(marker='profile-current').type('seguridad123')
    user.find(marker='profile-new').type('vigilancia7')
    user.find(marker='profile-confirmation').type('vigilancia7')
    user.find('Actualizar contraseña').click()
    await user.should_see('Contraseña actualizada.', retries=LOGIN_RETRIES)
    user.find('Cerrar sesión').click()
    await user.should_see('Iniciar sesión')  # que termine la navegación
    await login(user, 'carlos.ruiz@lumina.es', 'vigilancia7')
    await user.should_see('Dashboard · Seguridad', retries=LOGIN_RETRIES)


async def test_a_deactivated_account_loses_its_open_pages(user: User, data_dir: Path) -> None:
    await login(user, 'carlos.ruiz@lumina.es', 'seguridad123')
    await user.should_see('Dashboard · Seguridad', retries=LOGIN_RETRIES)
    await user.open('/perfil')
    edit_user(data_dir, 'usr-carlos', activo=False)
    user.find('Guardar cambios').click()
    await user.should_see('Iniciar sesión')


async def test_saving_the_profile_with_unreadable_accounts_shows_an_error(user: User, data_dir: Path) -> None:
    await login(user, 'marta.garcia@lumina.es', 'gerente123')
    await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
    await user.open('/perfil')
    await user.should_see('Datos personales')
    (data_dir / 'usuarios.json').write_text('{"usuarios": [', encoding='utf-8')
    user.find('Guardar cambios').click()
    await user.should_see('usuarios.json')  # un aviso, no un error sin capturar


async def test_logging_out_always_ends_the_session(user: User, data_dir: Path) -> None:
    await login(user, 'marta.garcia@lumina.es', 'gerente123')
    await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
    (data_dir / 'usuarios.json').write_text('{"usuarios": [', encoding='utf-8')  # no se puede guardar
    user.find('Cerrar sesión').click()
    await user.should_see('Iniciar sesión')
    await user.open('/dashboard')
    await user.should_see('Iniciar sesión')
