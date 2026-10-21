"""Raíz de composición: crea el Modelo, los Controladores y la Vista y arranca NiceGUI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, ClassVar

from nicegui import app, ui

from .controllers import Services
from .repositories import Repositories
from .settings import APP_NAME, FROZEN, AppSettings
from .views import Router, Theme, ViewContext
from .views.components import Box, Button, Heading, Text
from .views.pages import PROTECTED_PAGES, PUBLIC_PAGES
from .views.routes import Route

log = logging.getLogger(__name__)


class LuminaApp:
    """Aplicación Lumina.

    ``services`` permite inyectar otros controladores (por ejemplo, con repositorios de
    base de datos en la fase 2 o con un reloj fijo en los tests).
    """

    WINDOW_SIZE: ClassVar[tuple[int, int]] = (1200, 760)
    WINDOW_MIN_SIZE: ClassVar[tuple[int, int]] = (400, 520)
    WINDOW_TEXTS: ClassVar[dict[str, str]] = {
        'global.quitConfirmation': '¿Seguro que quieres salir?',
        'global.ok': 'Aceptar',
        'global.quit': 'Salir',
        'global.cancel': 'Cancelar',
        'global.saveFile': 'Guardar archivo',
        'cocoa.menu.about': 'Acerca de',
        'cocoa.menu.services': 'Servicios',
        'cocoa.menu.view': 'Visualización',
        'cocoa.menu.edit': 'Edición',
        'cocoa.menu.hide': 'Ocultar',
        'cocoa.menu.hideOthers': 'Ocultar otros',
        'cocoa.menu.showAll': 'Mostrar todo',
        'cocoa.menu.quit': 'Salir de',
        'cocoa.menu.fullscreen': 'Pantalla completa',
        'cocoa.menu.cut': 'Cortar',
        'cocoa.menu.copy': 'Copiar',
        'cocoa.menu.paste': 'Pegar',
        'cocoa.menu.selectAll': 'Seleccionar todo',
        'windows.fileFilter.allFiles': 'Todos los archivos',
        'windows.fileFilter.otherFiles': 'Otros tipos de archivo',
        'linux.openFile': 'Abrir archivo',
        'linux.openFiles': 'Abrir archivos',
        'linux.openFolder': 'Abrir carpeta',
    }
    """Textos de la ventana y del menú de la aplicación (pywebview los trae en inglés)."""

    def __init__(self, settings: AppSettings, *, services: Services | None = None) -> None:
        self._settings = settings
        self._services = services or Services.create(Repositories.from_json_dir(settings.data_dir))

    @property
    def services(self) -> Services:
        return self._services

    @property
    def reloads(self) -> bool:
        """Recarga en caliente activa (nunca en el ejecutable, que no tiene ficheros ``.py`` que vigilar)."""
        return self._settings.reload and not FROZEN

    def setup(self) -> None:
        """Registra recursos estáticos, colores y páginas."""
        Theme.install()
        app.add_static_files(Theme.ASSETS_URL, self._settings.assets_dir)
        app.on_page_exception(self._error_page)
        router = Router(ViewContext(self._services, self._settings))
        router.add_root()
        for public_page in PUBLIC_PAGES:
            router.add_public(public_page)
        for protected_page in PROTECTED_PAGES:
            router.add_protected(protected_page)

    def run(self) -> None:
        """Configura la aplicación y la abre en una ventana de escritorio (o en el navegador)."""
        self.setup()
        settings = self._settings
        if settings.native:
            self._setup_window()
        ui.run(
            host=settings.host,
            port=settings.port,
            title=APP_NAME,
            favicon=self._favicon(),
            dark=settings.dark_mode,
            language='es',
            storage_secret=settings.storage_secret,
            reload=self.reloads,
            show=settings.open_browser,
            native=settings.native,
            window_size=self.WINDOW_SIZE if settings.native else None,
            **self._server_logging(),
        )

    @staticmethod
    def _server_logging() -> dict[str, Any]:
        """En el ejecutable, uvicorn deja sus mensajes en ``lumina.log`` (ver :mod:`lumina.launcher`)."""
        return {'log_config': None} if FROZEN else {}

    def _favicon(self) -> Path | None:
        """Icono de la página.

        En Windows, NiceGUI usa el favicon como icono de la ventana de escritorio y solo admite
        ``.ico``; sin él, la ventana muestra el icono del ejecutable.
        """
        if self._settings.native and sys.platform == 'win32':
            return None
        return self._settings.assets_dir / 'logo-icono.png'

    def _setup_window(self) -> None:
        """Ventana de escritorio (pywebview): texto seleccionable como en la web y menús en español."""
        app.native.window_args.update(min_size=self.WINDOW_MIN_SIZE, text_select=True)
        app.native.start_args['localization'] = dict(self.WINDOW_TEXTS)
        if not self.reloads:
            # Cerrar la ventana termina la aplicación y, con ella, las sesiones. Con la recarga en
            # caliente el servidor se reinicia a menudo sin que nadie salga, así que no se hace.
            app.on_shutdown(self._services.auth.close_sessions)

    @staticmethod
    def _error_page(error: Exception) -> None:
        """Página amable cuando falla la construcción de una pantalla (p. ej. un JSON mal formado)."""
        log.exception('Error al construir la página', exc_info=error)
        Theme.apply_to_page()
        with Box('w-full max-w-[560px] mx-auto px-6 py-12'):
            Heading('No se ha podido mostrar la página')
            Text('Se ha producido un error al cargar los datos:', tag='p', classes=f'{Theme.MUTED} mb-3')
            Text(str(error), tag='p', classes=f'font-mono text-sm rounded px-3 py-2 mb-5 {Theme.CODE}')
            Button('Volver al inicio', href=Route.ROOT)
