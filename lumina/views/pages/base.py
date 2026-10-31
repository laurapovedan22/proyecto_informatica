"""Clases base de las páginas.

Cada visita a una ruta crea una instancia nueva de la página (el estado nunca se comparte
entre usuarios). :class:`lumina.views.router.Router` se encarga de comprobar la sesión y
los permisos antes de construirla, y :meth:`ProtectedPage.current_user` vuelve a hacerlo
en cada acción y en cada refresco mientras la página sigue abierta.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar, Generic, TypeVar

from nicegui import ui

from ...controllers import LuminaError, Services
from ...models import Permission, Role, User
from ...repositories import DataFormatError
from ...settings import AppSettings
from ..components import AppShell, AuthShell
from ..context import ViewContext
from ..routes import Route
from ..theme import Theme

T = TypeVar('T')

log = logging.getLogger(__name__)


class Page(ABC):
    """Pantalla de la aplicación asociada a una ruta."""

    route: ClassVar[Route]
    title: ClassVar[str]

    def __init__(self, context: ViewContext) -> None:
        self._context = context

    @property
    def services(self) -> Services:
        return self._context.services

    @property
    def settings(self) -> AppSettings:
        return self._context.settings

    @abstractmethod
    def build(self) -> None:
        """Construye la interfaz de la página."""

    @staticmethod
    def run_action(action: Callable[[], object], *, success: str | None = None) -> bool:
        """Ejecuta una acción de un controlador mostrando el error (o el éxito) como notificación."""
        try:
            action()
        except LuminaError as error:
            ui.notify(str(error), type='negative')
            return False
        except (DataFormatError, OSError) as error:
            Page.report_data_error(error, 'No se ha completado la acción')
            return False
        if success:
            ui.notify(success, type='positive')
        return True

    @staticmethod
    def report_data_error(error: DataFormatError | OSError, intro: str) -> None:
        log.warning('%s: %s', intro, error)
        ui.notify(f'{intro}: {error}', type='negative', multi_line=True)


class PublicPage(Page):
    """Página accesible sin sesión (inicio de sesión y registro)."""

    def build(self) -> None:
        Theme.apply_to_page()
        with AuthShell().content:
            self.render()

    @abstractmethod
    def render(self) -> None:
        """Contenido bajo el logotipo."""


class ProtectedPage(Page):
    """Página que exige sesión y, opcionalmente, un permiso del rol."""

    permission: ClassVar[Permission | None] = None
    shell: AppShell
    """Estructura de la página; disponible desde que se llama a :meth:`build`."""

    def __init__(self, context: ViewContext, user: User) -> None:
        super().__init__(context)
        if user.role is None:
            raise ValueError('Una página privada necesita un usuario con perfil asignado')
        self.user = user
        self.role: Role = user.role

    @classmethod
    def allows(cls, user: User) -> bool:
        return cls.permission is None or user.can(cls.permission)

    def current_user(self) -> User | None:
        """Usuario vigente de la sesión, si esta página sigue siendo para él; si no, se le saca de ella.

        Las acciones y los refrescos se autorizan con este usuario, no con el de la carga de la
        página: desactivar una cuenta, cambiarle el perfil o cerrar su sesión en otra pestaña
        surte efecto en las páginas que ya tenía abiertas. Si la cuenta o el perfil han cambiado
        pero la página sigue permitida, se vuelve a construir (lo que muestra depende del perfil).

        Lanza :class:`DataFormatError` u :class:`OSError` si no se pueden leer las cuentas:
        entonces no se autoriza nada.
        """
        user = self._context.session().current_user()
        if user is None:
            ui.navigate.to(Route.LOGIN)
            return None
        if not self.allows(user):
            ui.navigate.to(Route.DASHBOARD)
            return None
        if (user.id, user.role) != (self.user.id, self.role):
            ui.navigate.to(self.route)
            return None
        return user

    def actor(self) -> User | None:
        """:meth:`current_user` para una acción: si no se pueden leer las cuentas, avisa y no autoriza."""
        try:
            return self.current_user()
        except (DataFormatError, OSError) as error:
            self.report_data_error(error, 'No se ha podido comprobar tu sesión')
            return None

    def act(self, action: Callable[[User], object], *, success: str | None = None) -> bool:
        """Como :meth:`run_action`, pero en nombre del usuario vigente (ver :meth:`actor`)."""
        actor = self.actor()
        return actor is not None and self.run_action(lambda: action(actor), success=success)

    def build(self) -> None:
        Theme.apply_to_page()
        self.shell = AppShell(self._context, self.user, active=self.route)
        with self.shell.content:
            self.render()

    @abstractmethod
    def render(self) -> None:
        """Contenido principal (a la derecha del menú)."""

    def live(self, loader: Callable[[], T], on_change: Callable[[], object]) -> LiveData[T]:
        """Datos que se releen cada ``refresh_seconds`` (si la sesión sigue siendo válida) y refrescan la vista."""
        return LiveData(
            loader, on_change, self.settings.refresh_seconds, allowed=lambda: self.current_user() is not None
        )


class LiveData(Generic[T]):
    """Valor obtenido de un controlador que se vuelve a leer periódicamente.

    Gracias a ello, si otro proceso modifica los JSON (un simulador o la maqueta IoT), la
    pantalla se actualiza sola. Solo se redibuja cuando el valor ha cambiado.
    """

    def __init__(
        self,
        loader: Callable[[], T],
        on_change: Callable[[], object],
        interval: float,
        *,
        allowed: Callable[[], bool] | None = None,
    ) -> None:
        self._loader = loader
        self._on_change = on_change
        self._allowed = allowed
        self._last_error: str | None = None
        self.value: T = loader()
        self._timer = ui.timer(interval, self.poll, immediate=False) if interval > 0 else None

    def poll(self) -> None:
        latest = self._read()
        if latest is not None and latest[0] != self.value:
            self.value = latest[0]
            self._on_change()

    def reload(self) -> None:
        """Relee los datos y redibuja (tras una acción del propio usuario, si aún puede verlos)."""
        latest = self._read()
        if latest is not None:
            self.value = latest[0]
            self._on_change()

    def _read(self) -> tuple[T] | None:
        """Datos actuales, o ``None`` si el usuario ya no puede verlos o no se pueden leer."""
        try:
            if self._allowed is not None and not self._allowed():
                if self._timer is not None:
                    self._timer.deactivate()  # la página ya no es para este usuario: deja de consultar
                return None
            latest = self._loader()
        except (DataFormatError, OSError) as error:
            if str(error) != self._last_error:
                Page.report_data_error(error, 'No se pudieron leer los datos')
                self._last_error = str(error)
            return None
        self._last_error = None
        return (latest,)
