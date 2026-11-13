"""Estructura común de las páginas: barra lateral + contenido, o pantalla de acceso."""

from __future__ import annotations

import logging

from nicegui import ui

from ...models import User
from ...repositories import DataFormatError
from ..context import ViewContext
from ..routes import Navigation, Route
from ..theme import Theme
from .base import Box, Picture, Text
from .buttons import Button, NavButton

log = logging.getLogger(__name__)


class Brand(Box):
    """Icono de Lumina con el nombre."""

    def __init__(self, *, large: bool = False) -> None:
        super().__init__(Theme.BRAND_LARGE if large else Theme.BRAND)
        with self:
            Picture(Theme.ICON_URL, alt='', classes=Theme.BRAND_ICON)
            Text('LUMINA')


class AppShell(Box):
    """Barra lateral con el menú del rol y zona de contenido (``lm-shell``)."""

    def __init__(self, context: ViewContext, user: User, *, active: Route) -> None:
        super().__init__(Theme.SHELL)
        self._context = context
        self._user = user
        with self:
            with Box(Theme.SIDEBAR, tag='aside'):
                Brand()
                with Box(Theme.USER_BOX):
                    self._user_name = Text(user.name, tag='p', classes=Theme.USER_NAME)
                    Text(user.role_label, tag='p', classes=Theme.ROLE)
                nav = Box(Theme.NAV, tag='nav')
                nav.props['aria-label'] = 'Menú principal'
                with nav:
                    for item in Navigation.for_user(user):
                        NavButton(item.label, href=item.route, active=item.route is active)
                Button('Cerrar sesión', on_click=self._logout).classes(Theme.LOGOUT).props('align=left')
            self.content = Box(Theme.CONTENT, tag='main')
        ui.skip_link('Ir al contenido principal', target=self.content)

    def show_user(self, user: User) -> None:
        """Actualiza el nombre mostrado en la barra lateral (tras editar el perfil)."""
        self._user = user
        self._user_name.set_text(user.name)

    def _logout(self) -> None:
        self._context.session().end()  # primero: la sesión se cierra aunque falle lo demás
        try:
            self._context.services.auth.logout(self._user.id)
        except (DataFormatError, OSError) as error:
            log.warning('No se pudo marcar la cuenta como desconectada: %s', error)
        ui.navigate.to(Route.LOGIN)


class AuthShell(Box):
    """Pantalla centrada de inicio de sesión y registro (``lm-auth``)."""

    def __init__(self) -> None:
        super().__init__(Theme.AUTH_PAGE, tag='main')
        with self:
            self.content = Box(Theme.AUTH_INNER)
            with self.content:
                Brand(large=True)
