"""Fuente de la fecha y hora actuales, inyectable para poder probar el código."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta


class Clock(ABC):
    """Reloj abstracto."""

    @abstractmethod
    def now(self) -> datetime:
        """Fecha y hora local actual, sin microsegundos."""

    def today(self) -> date:
        return self.now().date()


class SystemClock(Clock):
    """Reloj real del sistema."""

    def now(self) -> datetime:
        return datetime.now().replace(microsecond=0)


class FixedClock(Clock):
    """Reloj detenido en un instante (útil en tests y demostraciones)."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def advance(self, delta: timedelta) -> None:
        self._moment += delta
