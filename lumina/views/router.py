"""Registro de las páginas en NiceGUI con control de acceso por sesión y por rol."""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from .context import ViewContext
from .pages import ProtectedPage, PublicPage
from .routes import Route


class Router:
    """Asocia cada clase de página a su ruta.

    NiceGUI solo admite funciones libres como constructores de página, así que el router
    crea una pequeña función por ruta que instancia la página en cada visita. Si el
    usuario no puede verla, la función devuelve una redirección HTTP y la página no llega
    a construirse.
    """

    def __init__(self, context: ViewContext) -> None:
        self._context = context

    def add_root(self) -> None:
        context = self._context

        @ui.page(Route.ROOT)
        def root() -> RedirectResponse:
            user = context.session().current_user()
            return RedirectResponse(Route.DASHBOARD if user is not None else Route.LOGIN)

    def add_public(self, page_type: type[PublicPage]) -> None:
        context = self._context

        @ui.page(page_type.route, title=self._title(page_type.title))
        def build_public() -> RedirectResponse | None:
            if context.session().current_user() is not None:
                return RedirectResponse(Route.DASHBOARD)
            page_type(context).build()
            return None

    def add_protected(self, page_type: type[ProtectedPage]) -> None:
        context = self._context

        @ui.page(page_type.route, title=self._title(page_type.title))
        def build_protected() -> RedirectResponse | None:
            user = context.session().current_user()
            if user is None:
                return RedirectResponse(Route.LOGIN)
            if not page_type.allows(user):
                return RedirectResponse(Route.DASHBOARD)
            page_type(context, user).build()
            return None

    @staticmethod
    def _title(title: str) -> str:
        return f'{title} · Lumina'
