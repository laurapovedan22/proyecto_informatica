"""Inicio de sesión, solicitud de cuenta y cierre de sesión (H1.2 / RF-01)."""

from __future__ import annotations

import logging
import threading
from functools import partial
from typing import ClassVar, NoReturn

from ..models import User
from ..repositories import DuplicateError, UserRepository
from .clock import Clock
from .errors import AuthenticationError, ValidationError
from .security import IdGenerator, PasswordHasher, UserInputValidator

log = logging.getLogger(__name__)


class AuthController:
    """Gestiona el acceso de los usuarios a la plataforma."""

    MAX_FAILED_ATTEMPTS: ClassVar[int] = 3
    """Contraseñas incorrectas seguidas que bloquean la cuenta hasta que la desbloquee un administrador."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher, clock: Clock) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock
        self._open_sessions: set[str] = set()
        self._closing = False
        self._sessions_lock = threading.Lock()
        """Protege ``_open_sessions`` y ``_closing``; iniciar y cerrar sesión lo mantienen mientras confirman."""

    def login(self, email: str, password: str) -> User:
        """Valida las credenciales y marca al usuario como conectado.

        Cada contraseña incorrecta suma un intento fallido a la cuenta. Con
        :attr:`MAX_FAILED_ATTEMPTS` seguidos la cuenta se bloquea y ya no admite inicios de sesión,
        ni siquiera con la contraseña correcta, hasta que un administrador la desbloquee.
        """
        user = self._users.find_by_email(email)
        if user is None:
            raise AuthenticationError('Correo o contraseña incorrectos.')
        if user.locked:
            raise self._locked_error()
        if not self._hasher.verify(password, user.password_hash):
            self._reject_password(user)
        # Verificar la contraseña tarda: el cambio se aplica sobre la versión actual de la cuenta,
        # por si entretanto la han desactivado, le han cambiado el perfil o la contraseña.
        with self._sessions_lock:
            if self._closing:
                raise AuthenticationError('La aplicación se está cerrando.')
            signed_in = self._users.modify(user.id, partial(self._sign_in, password_hash=user.password_hash))
            if signed_in is None:
                raise AuthenticationError('Correo o contraseña incorrectos.')
            self._open_sessions.add(signed_in.id)
        return signed_in

    def _sign_in(self, current: User, *, password_hash: str) -> User:
        if current.password_hash != password_hash:
            raise AuthenticationError('Correo o contraseña incorrectos.')
        if current.locked:
            raise self._locked_error()
        if not current.active:
            raise AuthenticationError('Tu cuenta está desactivada. Contacta con el administrador.')
        if current.role is None:
            raise AuthenticationError('Tu solicitud de cuenta está pendiente de aprobación por el administrador.')
        return current.signed_in(self._clock.now())

    def _reject_password(self, user: User) -> NoReturn:
        """Anota el intento fallido en la versión actual de la cuenta y avisa de cuántos quedan."""
        failed = self._users.modify(user.id, partial(self._count_failure, password_hash=user.password_hash))
        if failed is not None and failed.locked:
            raise self._locked_error()
        remaining = self.MAX_FAILED_ATTEMPTS - failed.failed_attempts if failed is not None else 0
        if remaining <= 0:
            raise AuthenticationError('Correo o contraseña incorrectos.')
        left = 'Te queda 1 intento' if remaining == 1 else f'Te quedan {remaining} intentos'
        raise AuthenticationError(f'Correo o contraseña incorrectos. {left} antes de que se bloquee la cuenta.')

    def _count_failure(self, current: User, *, password_hash: str) -> User:
        # Si la contraseña ha cambiado mientras se comprobaba, el intento no se cuenta contra la nueva.
        if current.locked or current.password_hash != password_hash:
            return current
        return current.with_failed_attempt(self.MAX_FAILED_ATTEMPTS)

    def _locked_error(self) -> AuthenticationError:
        return AuthenticationError(
            f'Tu cuenta está bloqueada tras {self.MAX_FAILED_ATTEMPTS} contraseñas incorrectas seguidas. '
            'Pide al administrador que la desbloquee.'
        )

    def logout(self, user_id: str) -> None:
        # Con el mismo cerrojo que el inicio de sesión, para que no se crucen el de una y el otro.
        with self._sessions_lock:
            self._users.modify(user_id, lambda current: current.signed_out())
            self._open_sessions.discard(user_id)  # después de guardar: si falla, close_sessions lo reintenta

    def close_sessions(self) -> None:
        """Cierra las sesiones iniciadas desde este proceso y no cerradas después.

        La aplicación de escritorio lo hace al cerrar la ventana, que termina la sesión: así
        nadie queda «conectado» en ``usuarios.json`` después de salir. A partir de entonces se
        rechaza cualquier inicio de sesión que aún estuviera en curso.
        """
        with self._sessions_lock:
            self._closing = True
            user_ids = sorted(self._open_sessions)
        for user_id in user_ids:
            try:
                self.logout(user_id)
            except (OSError, ValueError):  # p. ej. un JSON mal formado: se cierran las demás
                log.exception('No se pudo cerrar la sesión del usuario %s', user_id)

    def register(self, name: str, email: str, password: str, confirmation: str) -> User:
        """Crea una solicitud de cuenta sin perfil: el administrador asignará el rol."""
        clean_name = UserInputValidator.name(name)
        clean_email = UserInputValidator.email(email)
        UserInputValidator.new_password(password, confirmation)
        if self._users.find_by_email(clean_email) is not None:
            raise ValidationError('Ya existe una cuenta con ese correo electrónico.')
        user = User(
            id=IdGenerator.new('usr'),
            name=clean_name,
            email=clean_email,
            password_hash=self._hasher.hash(password),
            role=None,
            created_at=self._clock.now(),
        )
        try:
            self._users.add(user)  # comprueba de nuevo el correo, ya con el fichero bloqueado
        except DuplicateError as error:
            raise ValidationError('Ya existe una cuenta con ese correo electrónico.') from error
        return user

    def session_user(self, user_id: str | None) -> User | None:
        """Usuario de una sesión, o ``None`` si ya no existe o ha perdido el acceso."""
        if user_id is None:
            return None
        user = self._users.get(user_id)
        return user if user is not None and user.can_sign_in else None
