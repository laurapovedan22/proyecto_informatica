"""Pantallas de Lumina (Sprint 1)."""

from .auth import LoginPage, RegisterPage
from .base import LiveData, Page, ProtectedPage, PublicPage
from .dashboard import DashboardPage
from .profile import ProfilePage
from .users import UsersPage

PUBLIC_PAGES: tuple[type[PublicPage], ...] = (LoginPage, RegisterPage)
PROTECTED_PAGES: tuple[type[ProtectedPage], ...] = (DashboardPage, UsersPage, ProfilePage)

__all__ = [
    'PROTECTED_PAGES',
    'PUBLIC_PAGES',
    'DashboardPage',
    'LiveData',
    'LoginPage',
    'Page',
    'ProfilePage',
    'ProtectedPage',
    'PublicPage',
    'RegisterPage',
    'UsersPage',
]
