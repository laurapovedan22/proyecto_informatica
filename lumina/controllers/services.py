"""Composición de todos los controladores a partir de los repositorios."""

from __future__ import annotations

from dataclasses import dataclass

from ..repositories import Repositories
from .auth import AuthController
from .clock import Clock, SystemClock
from .facility import FacilityController
from .security import PasswordHasher
from .simulation import LiveSimulator
from .supervision import SupervisionController
from .users import UserController


@dataclass(frozen=True, slots=True)
class Services:
    """Controladores disponibles para las vistas de los Sprints 1 y 2, y la simulación en vivo."""

    clock: Clock
    auth: AuthController
    users: UserController
    facility: FacilityController
    supervision: SupervisionController
    simulation: LiveSimulator

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
            facility=FacilityController(repositories, clock),
            supervision=SupervisionController(repositories, clock),
            simulation=LiveSimulator(repositories, clock),
        )
