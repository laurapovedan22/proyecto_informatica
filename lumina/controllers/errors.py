"""Errores de negocio. Su mensaje está pensado para mostrarse tal cual al usuario."""

from __future__ import annotations

from ..models import Permission, User


class LuminaError(Exception):
    """Error de negocio con un mensaje apto para la interfaz."""


class ValidationError(LuminaError):
    """Los datos introducidos no son válidos."""


class NotFoundError(LuminaError):
    """El elemento solicitado no existe (o ya no existe)."""


class PermissionDeniedError(LuminaError):
    """El usuario no tiene permiso para realizar la acción."""

    @classmethod
    def require(cls, user: User, permission: Permission) -> None:
        """Lanza el error si ``user`` no tiene ``permission``.

        Las vistas ya ocultan lo que un rol no puede usar; esta comprobación es la segunda
        barrera, por si alguien llama al controlador directamente.
        """
        if not user.can(permission):
            raise cls('No tienes permiso para realizar esta acción.')


class AuthenticationError(LuminaError):
    """Credenciales incorrectas o cuenta sin acceso."""
