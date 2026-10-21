"""Lógica de negocio del Sprint 1: autenticación (H1.2), gestión de usuarios (H1.3) y perfil (H1.4)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lumina.controllers import (
    AuthenticationError,
    FixedClock,
    PasswordHasher,
    PermissionDeniedError,
    Services,
    ValidationError,
)
from lumina.models import Role, User
from lumina.repositories import Repositories


class InterruptingHasher(PasswordHasher):
    """Ejecuta ``meanwhile`` (una sola vez) mientras «calcula» un hash, como si otro usuario actuara a la vez."""

    def __init__(self) -> None:
        super().__init__(iterations=1_000)
        self.meanwhile: Callable[[], object] | None = None

    def verify(self, password: str, encoded: str) -> bool:
        result = super().verify(password, encoded)
        self._interrupt()
        return result

    def hash(self, password: str) -> str:
        result = super().hash(password)
        self._interrupt()
        return result

    def _interrupt(self) -> None:
        action, self.meanwhile = self.meanwhile, None
        if action is not None:
            action()


@pytest.fixture
def hasher() -> InterruptingHasher:
    return InterruptingHasher()


@pytest.fixture
def racing_services(repositories: Repositories, clock: FixedClock, hasher: InterruptingHasher) -> Services:
    return Services.create(repositories, clock=clock, hasher=hasher)


def stored(repositories: Repositories, user_id: str) -> User:
    user = repositories.users.get(user_id)
    assert user is not None
    return user


# --- H1.2 · Inicio y cierre de sesión, solicitud de cuenta -----------------------------------


def test_valid_credentials_sign_in_with_the_users_role(services: Services, repositories: Repositories) -> None:
    user = services.auth.login('MARTA.GARCIA@lumina.es ', 'gerente123')
    assert user.role is Role.MANAGER and user.connected
    assert stored(repositories, 'usr-marta').connected


def test_invalid_credentials_are_rejected(services: Services) -> None:
    with pytest.raises(AuthenticationError, match='incorrectos'):
        services.auth.login('ana.lopez@lumina.es', 'otra')
    with pytest.raises(AuthenticationError, match='incorrectos'):
        services.auth.login('nadie@lumina.es', 'admin123')


def test_a_new_request_waits_for_the_administrator(services: Services, admin: User) -> None:
    request = services.auth.register('  Lucía   Fernández ', 'Lucia@Lumina.es', 'secreta1', 'secreta1')
    assert (request.name, request.email, request.role) == ('Lucía Fernández', 'lucia@lumina.es', None)
    assert services.users.list_users()[0].id == request.id  # las solicitudes aparecen primero
    with pytest.raises(AuthenticationError, match='pendiente de aprobación'):
        services.auth.login('lucia@lumina.es', 'secreta1')
    services.users.change_role(request.id, Role.MANAGER, admin)  # aprobarla es asignarle un perfil
    assert services.auth.login('lucia@lumina.es', 'secreta1').role is Role.MANAGER


@pytest.mark.parametrize(
    ('name', 'email', 'password', 'confirmation', 'message'),
    [
        ('', 'a@b.es', 'secreta1', 'secreta1', 'nombre es obligatorio'),
        ('Ana', 'no-es-un-correo', 'secreta1', 'secreta1', 'correo electrónico válido'),
        ('Ana', 'a@b.es', 'corta', 'corta', 'al menos 6 caracteres'),
        ('Ana', 'a@b.es', 'secreta1', 'secreta2', 'no coinciden'),
        ('Ana', 'ana.lopez@lumina.es', 'secreta1', 'secreta1', 'Ya existe una cuenta'),
    ],
)
def test_registration_validation(
    services: Services, name: str, email: str, password: str, confirmation: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        services.auth.register(name, email, password, confirmation)


def test_logout_marks_the_user_as_disconnected(services: Services, repositories: Repositories) -> None:
    services.auth.login('marta.garcia@lumina.es', 'gerente123')
    services.auth.logout('usr-marta')
    assert not stored(repositories, 'usr-marta').connected


def test_closing_the_app_signs_out_its_open_sessions(services: Services, repositories: Repositories) -> None:
    services.auth.login('marta.garcia@lumina.es', 'gerente123')
    services.auth.close_sessions()
    assert not stored(repositories, 'usr-marta').connected
    assert stored(repositories, 'usr-carlos').connected  # su sesión no se abrió desde esta aplicación


def test_an_account_deactivated_while_logging_in_stays_deactivated(
    racing_services: Services, repositories: Repositories, hasher: InterruptingHasher, manager: User
) -> None:
    hasher.meanwhile = lambda: repositories.users.update(manager.with_active(False))
    with pytest.raises(AuthenticationError, match='desactivada'):
        racing_services.auth.login('marta.garcia@lumina.es', 'gerente123')
    marta = stored(repositories, 'usr-marta')
    assert not marta.active and not marta.connected


def test_a_login_that_finishes_after_closing_the_app_is_rejected(
    racing_services: Services, repositories: Repositories, hasher: InterruptingHasher
) -> None:
    hasher.meanwhile = racing_services.auth.close_sessions  # la ventana se cierra durante el inicio de sesión
    with pytest.raises(AuthenticationError, match='cerrando'):
        racing_services.auth.login('marta.garcia@lumina.es', 'gerente123')
    assert not stored(repositories, 'usr-marta').connected


def test_two_registrations_cannot_share_an_email(
    racing_services: Services, repositories: Repositories, hasher: InterruptingHasher
) -> None:
    register = racing_services.auth.register
    hasher.meanwhile = lambda: register('Lucía Fernández', 'lucia@lumina.es', 'secreta1', 'secreta1')
    with pytest.raises(ValidationError, match='Ya existe'):
        register('Lucía F.', 'LUCIA@lumina.es', 'secreta2', 'secreta2')
    assert sum(user.email == 'lucia@lumina.es' for user in repositories.users.list_all()) == 1


# --- H1.3 · Administración de cuentas y roles -------------------------------------------------


def test_admin_creates_a_user_with_a_temporary_password(services: Services, admin: User) -> None:
    credentials = services.users.create('Pedro Gil', 'pedro@lumina.es', Role.SECURITY, admin)
    assert credentials.user.role is Role.SECURITY
    assert services.auth.login('pedro@lumina.es', credentials.temporary_password).id == credentials.user.id


def test_admin_edits_an_account(services: Services, repositories: Repositories, admin: User) -> None:
    updated = services.users.update_account('usr-marta', '  Marta   García Ruiz ', 'MARTA.G@lumina.es', admin)
    assert (updated.name, updated.email) == ('Marta García Ruiz', 'marta.g@lumina.es')
    assert stored(repositories, 'usr-marta').email == 'marta.g@lumina.es'
    assert services.auth.login('marta.g@lumina.es', 'gerente123').id == 'usr-marta'


def test_an_edited_account_cannot_take_another_email(services: Services, admin: User) -> None:
    with pytest.raises(ValidationError, match='Ya existe una cuenta'):
        services.users.update_account('usr-marta', 'Marta García', 'carlos.ruiz@lumina.es', admin)
    with pytest.raises(ValidationError, match='correo electrónico válido'):
        services.users.update_account('usr-marta', 'Marta García', 'marta', admin)


def test_admin_changes_roles_and_deactivates_accounts(
    services: Services, repositories: Repositories, admin: User
) -> None:
    assert services.users.change_role('usr-marta', Role.SECURITY, admin).role is Role.SECURITY
    services.users.set_active('usr-marta', False, admin)
    with pytest.raises(AuthenticationError, match='desactivada'):
        services.auth.login('marta.garcia@lumina.es', 'gerente123')
    services.users.set_active('usr-marta', True, admin)
    assert services.auth.login('marta.garcia@lumina.es', 'gerente123').role is Role.SECURITY
    assert services.users.counts().inactive == 0


def test_admin_cannot_change_their_own_account_from_the_list(services: Services, admin: User) -> None:
    with pytest.raises(ValidationError, match='tu propia cuenta'):
        services.users.set_active(admin.id, False, admin)
    with pytest.raises(ValidationError, match='tu propia cuenta'):
        services.users.update_account(admin.id, 'Otra', 'otra@lumina.es', admin)


def test_only_admins_manage_users(services: Services, security: User, manager: User) -> None:
    for actor in (security, manager):
        with pytest.raises(PermissionDeniedError):
            services.users.create('X', 'x@lumina.es', Role.ADMIN, actor)
        with pytest.raises(PermissionDeniedError):
            services.users.change_role('usr-ana', Role.MANAGER, actor)
        with pytest.raises(PermissionDeniedError):
            services.users.set_active('usr-ana', False, actor)
        with pytest.raises(PermissionDeniedError):
            services.users.update_account('usr-ana', 'Ana', 'ana@lumina.es', actor)


def test_a_demoted_admin_cannot_keep_editing(services: Services, repositories: Repositories, admin: User) -> None:
    repositories.users.update(admin.with_role(Role.MANAGER))  # otro administrador lo acaba de degradar
    with pytest.raises(PermissionDeniedError):
        services.users.update_account('usr-marta', 'Marta', 'marta@lumina.es', admin)  # con su copia antigua
    assert stored(repositories, 'usr-marta').email == 'marta.garcia@lumina.es'


def test_an_admin_demoted_while_creating_a_user_cannot_finish(
    racing_services: Services, repositories: Repositories, hasher: InterruptingHasher, admin: User
) -> None:
    hasher.meanwhile = lambda: repositories.users.update(admin.with_role(Role.MANAGER))
    with pytest.raises(PermissionDeniedError):
        racing_services.users.create('Lucía Fernández', 'lucia@lumina.es', Role.ADMIN, admin)
    assert repositories.users.find_by_email('lucia@lumina.es') is None


def test_a_role_change_keeps_a_concurrent_login(racing_services: Services, admin: User) -> None:
    racing_services.auth.login('marta.garcia@lumina.es', 'gerente123')
    updated = racing_services.users.change_role('usr-marta', Role.SECURITY, admin)
    assert updated.role is Role.SECURITY and updated.connected  # no vuelve a la copia de antes del login


def test_account_counts(services: Services, admin: User) -> None:
    services.auth.register('Lucía Fernández', 'lucia@lumina.es', 'secreta1', 'secreta1')
    services.users.set_active('usr-marta', False, admin)
    counts = services.users.counts()
    assert (counts.total, counts.connected, counts.pending, counts.inactive) == (4, 1, 1, 1)


# --- H1.4 · Perfil propio --------------------------------------------------------------------


def test_user_updates_their_profile(services: Services, repositories: Repositories) -> None:
    updated = services.users.update_profile('usr-marta', 'Marta García López', 'marta@lumina.es')
    assert (updated.name, updated.email) == ('Marta García López', 'marta@lumina.es')
    assert stored(repositories, 'usr-ana').email == 'ana.lopez@lumina.es'  # nadie más cambia
    with pytest.raises(ValidationError, match='Ya existe una cuenta'):
        services.users.update_profile('usr-marta', 'Marta', 'ana.lopez@lumina.es')


def test_user_changes_their_password(services: Services) -> None:
    with pytest.raises(AuthenticationError, match='actual no es correcta'):
        services.users.change_password('usr-marta', 'mal', 'nueva123', 'nueva123')
    with pytest.raises(ValidationError, match='no coinciden'):
        services.users.change_password('usr-marta', 'gerente123', 'nueva123', 'otra123')
    services.users.change_password('usr-marta', 'gerente123', 'nueva123', 'nueva123')
    assert services.auth.login('marta.garcia@lumina.es', 'nueva123').id == 'usr-marta'


def test_a_password_changed_meanwhile_is_not_overwritten(
    racing_services: Services, repositories: Repositories, hasher: InterruptingHasher, manager: User
) -> None:
    other_hash = PasswordHasher(iterations=1_000).hash('desde-otra-sesion')
    hasher.meanwhile = lambda: repositories.users.update(manager.with_password_hash(other_hash))
    with pytest.raises(AuthenticationError, match='acaba de cambiar'):
        racing_services.users.change_password('usr-marta', 'gerente123', 'nueva123', 'nueva123')
    assert stored(repositories, 'usr-marta').password_hash == other_hash


def test_a_deactivated_account_cannot_finish_changing_its_password(
    racing_services: Services, repositories: Repositories, hasher: InterruptingHasher, manager: User
) -> None:
    hasher.meanwhile = lambda: repositories.users.update(manager.with_active(False))
    with pytest.raises(AuthenticationError, match='ya no tiene acceso'):
        racing_services.users.change_password('usr-marta', 'gerente123', 'nueva123', 'nueva123')
    assert stored(repositories, 'usr-marta').password_hash == manager.password_hash
