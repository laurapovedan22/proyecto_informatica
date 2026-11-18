"""Autorización con la versión estricta de la cuenta dentro de una transacción."""

from ..models import Permission, User
from ..repositories import UserRepository
from .errors import PermissionDeniedError


def require_actor(users: UserRepository, actor: User, permission: Permission) -> User:
    """Revalida el acceso y devuelve el nombre vigente del responsable sin escribir la cuenta."""

    def check(current: User) -> User:
        if not current.can_sign_in:
            raise PermissionDeniedError('Tu cuenta ya no tiene acceso.')
        PermissionDeniedError.require(current, permission)
        return current

    current = users.modify(actor.id, check)
    if current is None:
        raise PermissionDeniedError('Tu cuenta ya no existe.')
    return current
