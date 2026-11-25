"""Estructura común de las páginas: barra lateral + contenido, o pantalla de acceso."""

from __future__ import annotations

import logging
from collections.abc import Callable

from nicegui import ui

from ...controllers import SupervisionController
from ...models import Permission, User, ZoneAlert
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
        watches_alerts = user.can(Permission.MANAGE_ALERTS)
        open_alerts: tuple[ZoneAlert, ...] | None = ()
        if watches_alerts:
            try:
                open_alerts = context.services.supervision.open_alerts()
            except (DataFormatError, OSError) as error:
                log.warning('No se pudo cargar el contador de alertas: %s', error)
                open_alerts = None  # el observador establecerá su referencia con la primera lectura válida
        badge: Text | None = None
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
                        with NavButton(item.label, href=item.route, active=item.route is active):
                            if item.route is Route.SUPERVISION and watches_alerts:
                                badge = Text(str(len(open_alerts or ())), classes=Theme.BADGE)
                                badge.set_visibility(bool(open_alerts))
                Button('Cerrar sesión', on_click=self._logout).classes(Theme.LOGOUT).props('align=left')
            self.content = Box(Theme.CONTENT, tag='main')
        ui.skip_link('Ir al contenido principal', target=self.content)
        self._watcher: AlertWatcher | None = None
        if watches_alerts:
            self._watcher = AlertWatcher(
                context.services.supervision,
                open_alerts,
                badge,
                context.settings.refresh_seconds,
                allowed=self._still_watches_alerts,
            )

    def refresh_alerts(self) -> None:
        """Actualiza el contador también tras una acción cuando el refresco está desactivado."""
        if self._watcher is not None:
            self._watcher.check()

    def show_user(self, user: User) -> None:
        """Actualiza el nombre mostrado en la barra lateral (tras editar el perfil)."""
        self._user = user
        self._user_name.set_text(user.name)

    def _still_watches_alerts(self) -> bool:
        user = self._context.session().current_user()
        return user is not None and user.can(Permission.MANAGE_ALERTS)

    def _logout(self) -> None:
        self._context.session().end()  # primero: la sesión se cierra aunque falle lo demás
        try:
            self._context.services.auth.logout(self._user.id)
        except (DataFormatError, OSError) as error:
            log.warning('No se pudo registrar el cierre de sesión: %s', error)
        ui.navigate.to(Route.LOGIN)


class AlertWatcher:
    """Mientras la página está abierta, avisa de las alertas nuevas y actualiza el contador del menú."""

    def __init__(
        self,
        supervision: SupervisionController,
        initial: tuple[ZoneAlert, ...] | None,
        badge: Text | None,
        interval: float,
        *,
        allowed: Callable[[], bool] | None = None,
    ) -> None:
        self._supervision = supervision
        self._badge = badge
        self._allowed = allowed
        self._known = {item.alert.id for item in initial} if initial is not None else None
        self._timer = ui.timer(interval, self.check, immediate=False) if interval > 0 else None

    def check(self) -> None:
        try:
            if self._allowed is not None and not self._allowed():
                if self._timer is not None:
                    self._timer.deactivate()  # ya no puede ver las alertas: deja de consultarlas
                return
            alerts = self._supervision.open_alerts()
        except (DataFormatError, OSError):
            return  # sin poder leer los datos no se muestra nada; el aviso ya lo da la página (LiveData)
        for item in alerts:
            if self._known is not None and item.alert.id not in self._known:
                ui.notify(
                    f'Nueva alerta: {item.alert.type.label} · {item.zone.name}',
                    type='warning',
                    position='top-right',
                    close_button='Cerrar',
                )
        self._known = {item.alert.id for item in alerts}
        if self._badge is not None:
            self._badge.set_text(str(len(alerts)))
            self._badge.set_visibility(bool(alerts))


class AuthShell(Box):
    """Pantalla centrada de inicio de sesión y registro (``lm-auth``)."""

    def __init__(self) -> None:
        super().__init__(Theme.AUTH_PAGE, tag='main')
        with self:
            self.content = Box(Theme.AUTH_INNER)
            with self.content:
                Brand(large=True)
