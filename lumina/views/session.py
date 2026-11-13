"""Sesión del navegador: qué usuario ha iniciado sesión (``app.storage.user``)."""

from __future__ import annotations

from nicegui import app

from ..controllers import AuthController
from ..models import User


class UserSession:
    """Guarda el identificador del usuario en el almacenamiento por usuario de NiceGUI."""

    _KEY = 'user_id'

    def __init__(self, auth: AuthController) -> None:
        self._auth = auth

    @property
    def user_id(self) -> str | None:
        value = app.storage.user.get(self._KEY)
        return value if isinstance(value, str) else None

    def current_user(self) -> User | None:
        """Usuario de la sesión; si ya no tiene acceso, la sesión se cierra."""
        user = self._auth.session_user(self.user_id)
        if user is None and self._KEY in app.storage.user:
            self.end()
        return user

    def start(self, user: User) -> None:
        app.storage.user[self._KEY] = user.id

    def end(self) -> None:
        app.storage.user.pop(self._KEY, None)
