"""Composición de todos los controladores a partir de los repositorios."""

from __future__ import annotations

from dataclasses import dataclass

from ..repositories import Repositories
from .auth import AuthController
from .clock import Clock, SystemClock
from .security import PasswordHasher
from .users import UserController


@dataclass(frozen=True, slots=True)
class Services:
    """Controladores disponibles para las vistas (Sprint 1: acceso y usuarios)."""

    clock: Clock
    auth: AuthController
    users: UserController

    @classmethod
    def create(
        cls,
        repositories: Repositories,
        *,
        clock: Clock | None = None,
        hasher: PasswordHasher | None = None,
    ) -> Services:
        clock = clock or SystemClock()
        hasher = hasher or PasswordHasher()
        return cls(
            clock=clock,
            auth=AuthController(repositories.users, hasher, clock),
            users=UserController(repositories.users, hasher, clock),
        )
