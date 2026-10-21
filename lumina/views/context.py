"""Dependencias compartidas por todas las vistas."""

from __future__ import annotations

from dataclasses import dataclass

from ..controllers import Services
from ..settings import AppSettings
from .session import UserSession


@dataclass(frozen=True, slots=True)
class ViewContext:
    """Controladores y configuración que reciben las páginas al construirse."""

    services: Services
    settings: AppSettings

    def session(self) -> UserSession:
        """Sesión del navegador que está construyendo la página o atendiendo el evento."""
        return UserSession(self.services.auth)
