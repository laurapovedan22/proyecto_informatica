"""Parámetros de arranque de la aplicación.

No confundir con :class:`lumina.models.SystemConfig`, que guarda la configuración del
establecimiento (umbrales, aforo, zonas…) en ``data/configuracion.json``.

Este módulo no importa NiceGUI: :mod:`lumina.launcher` lo usa antes de cargarlo.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = 'Lumina'
"""Nombre que ve el usuario: título de la ventana y avisos."""

APP_EDITION = 'Lumina Sprint 1'
"""Nombre de esta entrega: el de su ejecutable y el de su carpeta de datos, para no mezclarlos con
los de otras versiones de Lumina instaladas en el mismo equipo."""

FROZEN = bool(getattr(sys, 'frozen', False))
"""``True`` dentro del ejecutable creado con ``scripts/empaquetar.py`` (PyInstaller)."""

RESOURCES_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
"""Código y recursos de solo lectura: la carpeta del proyecto o, en el ejecutable, la que prepara PyInstaller."""

SAMPLE_DATA_DIR = RESOURCES_DIR / 'data'
"""Datos de ejemplo. El ejecutable los copia en una carpeta de datos nueva la primera vez."""


def user_data_root(environ: Mapping[str, str] | None = None, *, platform: str = sys.platform) -> Path:
    """Carpeta de Lumina entre los datos del usuario, según el sistema operativo.

    La usa el ejecutable, que no puede escribir junto a sí mismo (``/Applications``,
    ``Program Files``…).
    """
    env = os.environ if environ is None else environ
    home = Path.home()
    if platform == 'darwin':
        return home / 'Library' / 'Application Support' / APP_EDITION
    if platform == 'win32':
        return Path(env.get('APPDATA') or home / 'AppData' / 'Roaming') / APP_EDITION
    return Path(env.get('XDG_DATA_HOME') or home / '.local' / 'share') / APP_EDITION.lower().replace(' ', '-')


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Configuración del arranque. Cada campo puede sobrescribirse con una variable ``LUMINA_*``."""

    data_dir: Path = user_data_root() / 'data' if FROZEN else SAMPLE_DATA_DIR
    """Carpeta con los JSON: ``data/`` del proyecto o, en el ejecutable, la de los datos del usuario."""
    assets_dir: Path = RESOURCES_DIR / 'assets'
    native: bool = True
    """Abre Lumina en una ventana de escritorio propia; ``False`` la sirve al navegador."""
    host: str = '127.0.0.1'
    port: int | None = None
    """``None`` elige el puerto solo: uno libre con la ventana de escritorio y el 8080 con el navegador."""
    storage_secret: str = 'lumina-dev-secret-cambiar-en-produccion'
    """Clave de las cookies de sesión. Con la ventana de escritorio, si no se indica, se genera una por ejecución."""
    reload: bool = False
    """Recarga al guardar ficheros ``.py`` (ayuda de desarrollo; el ejecutable nunca recarga)."""
    open_browser: bool = True
    """Abre el navegador al arrancar (solo cuando ``native`` es ``False``)."""
    dark_mode: bool | None = None
    """``None`` sigue el modo claro/oscuro del sistema operativo."""
    refresh_seconds: float = 5.0
    """Cada cuánto se releen los JSON para refrescar la interfaz (0 lo desactiva)."""
    demo_mode: bool = True
    """Muestra las cuentas de demostración en la pantalla de inicio de sesión."""

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppSettings:
        """Crea la configuración a partir de las variables de entorno (o de ``environ``)."""
        env = EnvironmentReader(os.environ if environ is None else environ)
        defaults = cls()
        return cls(
            data_dir=env.path('LUMINA_DATA_DIR', defaults.data_dir),
            assets_dir=env.path('LUMINA_ASSETS_DIR', defaults.assets_dir),
            native=env.flag('LUMINA_NATIVE', defaults.native),
            host=env.text('LUMINA_HOST', defaults.host),
            port=env.optional_integer('LUMINA_PORT', defaults.port),
            storage_secret=env.text('LUMINA_STORAGE_SECRET', defaults.storage_secret),
            reload=env.flag('LUMINA_RELOAD', defaults.reload),
            open_browser=env.flag('LUMINA_OPEN_BROWSER', defaults.open_browser),
            dark_mode=env.optional_flag('LUMINA_DARK_MODE', defaults.dark_mode),
            refresh_seconds=env.number('LUMINA_REFRESH_SECONDS', defaults.refresh_seconds),
            demo_mode=env.flag('LUMINA_DEMO_MODE', defaults.demo_mode),
        )


class EnvironmentReader:
    """Lee variables de entorno convirtiéndolas al tipo esperado."""

    _TRUE = frozenset({'1', 'true', 'si', 'sí', 'yes', 'on'})
    _FALSE = frozenset({'0', 'false', 'no', 'off'})

    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def text(self, name: str, default: str) -> str:
        value = self._environ.get(name, '').strip()
        return value or default

    def optional_integer(self, name: str, default: int | None) -> int | None:
        raw = self._environ.get(name, '').strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError as error:
            raise ValueError(f'{name} debe ser un número entero (valor recibido: {raw!r})') from error

    def number(self, name: str, default: float) -> float:
        raw = self._environ.get(name, '').strip()
        if not raw:
            return default
        try:
            return float(raw.replace(',', '.'))
        except ValueError as error:
            raise ValueError(f'{name} debe ser numérico (valor recibido: {raw!r})') from error

    def flag(self, name: str, default: bool) -> bool:
        value = self.optional_flag(name, default)
        return default if value is None else value

    def optional_flag(self, name: str, default: bool | None) -> bool | None:
        raw = self._environ.get(name, '').strip().casefold()
        if not raw:
            return default
        if raw == 'auto':
            return None
        if raw in self._TRUE:
            return True
        if raw in self._FALSE:
            return False
        raise ValueError(f'{name} debe ser true, false o auto (valor recibido: {raw!r})')

    def path(self, name: str, default: Path) -> Path:
        raw = self._environ.get(name, '').strip()
        return Path(raw).expanduser().resolve() if raw else default
