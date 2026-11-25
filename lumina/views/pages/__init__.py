"""Pantallas de Lumina (Sprints 1 a 3)."""

from .auth import LoginPage, RegisterPage
from .base import LiveData, Page, ProtectedPage, PublicPage
from .configuration import ConfigurationPage
from .dashboard import DashboardPage
from .profile import ProfilePage
from .supervision import SupervisionPage
from .users import UsersPage

PUBLIC_PAGES: tuple[type[PublicPage], ...] = (LoginPage, RegisterPage)
PROTECTED_PAGES: tuple[type[ProtectedPage], ...] = (
    DashboardPage,
    UsersPage,
    ProfilePage,
    SupervisionPage,
    ConfigurationPage,
)

__all__ = [
    'PROTECTED_PAGES',
    'PUBLIC_PAGES',
    'ConfigurationPage',
    'DashboardPage',
    'LiveData',
    'LoginPage',
    'Page',
    'ProfilePage',
    'ProtectedPage',
    'PublicPage',
    'RegisterPage',
    'SupervisionPage',
    'UsersPage',
]
