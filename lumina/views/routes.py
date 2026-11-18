"""Rutas de la aplicación y menú lateral según el rol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from ..models import Permission, User


class Route(StrEnum):
    """URL de cada pantalla entregada en los Sprints 1 a 3."""

    ROOT = '/'
    LOGIN = '/login'
    REGISTER = '/registro'
    DASHBOARD = '/dashboard'
    SUPERVISION = '/supervision'
    USERS = '/usuarios'
    PROFILE = '/perfil'
    CONFIGURATION = '/configuracion'


@dataclass(frozen=True, slots=True)
class NavItem:
    """Entrada del menú. ``permission=None`` la muestra a cualquier usuario autenticado."""

    route: Route
    label: str
    permission: Permission | None = None

    def visible_for(self, user: User) -> bool:
        return self.permission is None or user.can(self.permission)


class Navigation:
    """Menú principal: el mismo orden que el mockup, con las pantallas que ya existen."""

    ITEMS: ClassVar[tuple[NavItem, ...]] = (
        NavItem(Route.DASHBOARD, 'Dashboard'),
        NavItem(Route.SUPERVISION, 'Supervisión', Permission.SUPERVISE),
        NavItem(Route.CONFIGURATION, 'Configuración', Permission.CONFIGURE_SYSTEM),
        NavItem(Route.USERS, 'Usuarios', Permission.MANAGE_USERS),
        NavItem(Route.PROFILE, 'Mi perfil'),
    )

    @classmethod
    def for_user(cls, user: User) -> list[NavItem]:
        return [item for item in cls.ITEMS if item.visible_for(user)]
