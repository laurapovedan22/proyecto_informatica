"""Gestión de usuarios (H1.3 / RF-02) y del perfil propio (H1.4 / RF-03)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..models import Permission, Role, User, UserCounts
from ..repositories import DuplicateError, UserRepository
from .clock import Clock
from .errors import AuthenticationError, NotFoundError, PermissionDeniedError, ValidationError
from .security import IdGenerator, PasswordHasher, UserInputValidator


@dataclass(frozen=True, slots=True)
class NewUserCredentials:
    """Cuenta recién creada por el administrador junto con su contraseña temporal."""

    user: User
    temporary_password: str


class UserController:
    """Altas, edición, perfiles y estado de las cuentas."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher, clock: Clock) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock

    # --- Consultas -------------------------------------------------------------------------

    def list_users(self) -> list[User]:
        """Solicitudes pendientes primero; después, por orden alfabético."""
        return sorted(self._users.list_all(), key=lambda user: (not user.is_pending, user.name.casefold()))

    def counts(self) -> UserCounts:
        users = self._users.list_all()
        return UserCounts(
            total=len(users),
            connected=sum(1 for user in users if user.connected),
            pending=sum(1 for user in users if user.is_pending),
            inactive=sum(1 for user in users if not user.active),
        )

    def get(self, user_id: str) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise NotFoundError('El usuario ya no existe.')
        return user

    # --- Administración (solo administrador) ------------------------------------------------

    def create(self, name: str, email: str, role: Role, actor: User) -> NewUserCredentials:
        PermissionDeniedError.require(actor, Permission.MANAGE_USERS)
        clean_name = UserInputValidator.name(name)
        clean_email = UserInputValidator.email(email)
        self._ensure_email_available(clean_email)
        password = self._hasher.temporary_password()
        user = User(
            id=IdGenerator.new('usr'),
            name=clean_name,
            email=clean_email,
            password_hash=self._hasher.hash(password),
            role=role,
            created_at=self._clock.now(),
        )

        # El hash tarda: al guardar, en la misma transacción, se comprueba de nuevo el correo y que
        # quien da el alta siga teniendo la cuenta activa y el permiso.
        def actor_still_allowed(users: list[User]) -> None:
            current = next((item for item in users if item.id == actor.id), None)
            self._require_actor(current, Permission.MANAGE_USERS)

        try:
            self._users.add(user, check=actor_still_allowed)
        except DuplicateError as error:
            raise ValidationError('Ya existe una cuenta con ese correo electrónico.') from error
        return NewUserCredentials(user=user, temporary_password=password)

    def update_account(self, user_id: str, name: str, email: str, actor: User) -> User:
        """Corrige el nombre o el correo de otra cuenta (la propia se edita en «Mi perfil»)."""
        clean_name = UserInputValidator.name(name)
        clean_email = UserInputValidator.email(email)
        return self._change_account(user_id, actor, self._profile_change(clean_name, clean_email))

    def change_role(self, user_id: str, role: Role, actor: User) -> User:
        """Asigna un perfil; a una solicitud pendiente, aprobarla es asignarle uno."""
        return self._change_account(
            user_id, actor, lambda current: current if current.role is role else current.with_role(role)
        )

    def set_active(self, user_id: str, active: bool, actor: User) -> User:
        """Desactiva una cuenta (no podrá iniciar sesión) o la vuelve a activar."""
        return self._change_account(
            user_id, actor, lambda current: current if current.active == active else current.with_active(active)
        )

    # --- Perfil propio (cualquier usuario) -------------------------------------------------

    def update_profile(self, user_id: str, name: str, email: str) -> User:
        clean_name = UserInputValidator.name(name)
        clean_email = UserInputValidator.email(email)
        return self._modify(user_id, self._profile_change(clean_name, clean_email))

    def change_password(self, user_id: str, current: str, new: str, confirmation: str) -> None:
        user = self.get(user_id)
        if not self._hasher.verify(current, user.password_hash):
            raise AuthenticationError('La contraseña actual no es correcta.')
        UserInputValidator.new_password(new, confirmation)
        new_hash = self._hasher.hash(new)

        def change(latest: User) -> User:
            # El hash tarda en calcularse: si mientras tanto la cuenta ha cambiado, no se pisa nada.
            if not latest.can_sign_in:
                raise AuthenticationError('Tu cuenta ya no tiene acceso.')
            if latest.password_hash != user.password_hash:
                raise AuthenticationError('La contraseña acaba de cambiar. Vuelve a intentarlo.')
            return latest.with_password_hash(new_hash)

        self._modify(user_id, change)

    # --- Auxiliares -------------------------------------------------------------------------

    def _change_account(self, user_id: str, actor: User, change: Callable[[User], User]) -> User:
        """Cambia otra cuenta comprobando, en la misma transacción, que el actor sigue pudiendo hacerlo."""
        PermissionDeniedError.require(actor, Permission.MANAGE_USERS)
        if user_id == actor.id:
            raise ValidationError('No puedes modificar tu propia cuenta desde la gestión de usuarios.')

        def checked(current: User) -> User:
            self._require_actor(self._users.get(actor.id), Permission.MANAGE_USERS)
            return change(current)

        return self._modify(user_id, checked)

    def _profile_change(self, name: str, email: str) -> Callable[[User], User]:
        def change(user: User) -> User:
            if (name, email) == (user.name, user.email):
                return user
            if email != user.email:
                self._ensure_email_available(email)  # dentro del bloqueo: nadie lo ocupa a la vez
            return user.with_profile(name, email)

        return change

    @staticmethod
    def _require_actor(current: User | None, permission: Permission) -> None:
        """Comprueba al actor tal y como está ahora: puede haber perdido la cuenta o el permiso."""
        if current is None or not current.can_sign_in:
            raise PermissionDeniedError('Tu cuenta ya no tiene acceso.')
        PermissionDeniedError.require(current, permission)

    def _modify(self, user_id: str, change: Callable[[User], User]) -> User:
        """Aplica ``change`` a la versión actual de la cuenta (ver :meth:`UserRepository.modify`)."""
        updated = self._users.modify(user_id, change)
        if updated is None:
            raise NotFoundError('El usuario ya no existe.')
        return updated

    def _ensure_email_available(self, email: str) -> None:
        if self._users.find_by_email(email) is not None:
            raise ValidationError('Ya existe una cuenta con ese correo electrónico.')
