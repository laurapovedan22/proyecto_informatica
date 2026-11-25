"""Composición de todos los controladores a partir de los repositorios."""

from __future__ import annotations

from dataclasses import dataclass

from ..repositories import Repositories
from .auth import AuthController
from .clock import Clock, SystemClock
from .configuration import ConfigurationController
from .facility import FacilityController
from .rules import RulesController
from .security import PasswordHasher
from .simulation import LiveSimulator
from .supervision import SupervisionController
from .users import UserController
from .vision import FrameReader, PersonDetector, VisionController


@dataclass(frozen=True, slots=True)
class Services:
    """Controladores disponibles para las vistas de los Sprints 1 a 3, la simulación en vivo y el análisis de imagen."""

    clock: Clock
    auth: AuthController
    users: UserController
    facility: FacilityController
    supervision: SupervisionController
    configuration: ConfigurationController
    rules: RulesController
    simulation: LiveSimulator
    vision: VisionController

    @classmethod
    def create(
        cls,
        repositories: Repositories,
        *,
        clock: Clock | None = None,
        hasher: PasswordHasher | None = None,
        detector: PersonDetector | None = None,
        frames: FrameReader | None = None,
    ) -> Services:
        """``detector`` y ``frames`` son, por defecto, YOLO y OpenCV (que solo se cargan al analizar)."""
        clock = clock or SystemClock()
        hasher = hasher or PasswordHasher()
        if detector is None or frames is None:
            from .yolo import VideoFrameReader, YoloPersonDetector

            detector = detector or YoloPersonDetector()
            frames = frames or VideoFrameReader()
        rules = RulesController(repositories, clock)
        return cls(
            clock=clock,
            auth=AuthController(repositories.users, hasher, clock),
            users=UserController(repositories.users, hasher, clock),
            facility=FacilityController(repositories, clock),
            supervision=SupervisionController(repositories, clock, rules),
            configuration=ConfigurationController(repositories, rules),
            rules=rules,
            simulation=LiveSimulator(repositories, clock),
            vision=VisionController(repositories, clock, detector, frames),
        )
