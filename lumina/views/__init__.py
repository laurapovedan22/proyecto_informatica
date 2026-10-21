"""Vista: interfaz web construida exclusivamente con la API Python de NiceGUI.

No se usa JavaScript, Vue ni CSS escrito a mano: los estilos son clases Tailwind generadas
desde :mod:`lumina.views.theme`.
"""

from .context import ViewContext
from .router import Router
from .routes import Navigation, NavItem, Route
from .session import UserSession
from .theme import Palette, Theme

__all__ = ['NavItem', 'Navigation', 'Palette', 'Route', 'Router', 'Theme', 'UserSession', 'ViewContext']
