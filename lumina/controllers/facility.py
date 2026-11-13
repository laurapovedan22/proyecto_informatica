"""Consulta del establecimiento para los dashboards (H2.2 y H2.3)."""

from __future__ import annotations

from ..models import FacilityStatus, SensorType
from ..repositories import Repositories
from .analysis import FacilityAnalyzer
from .clock import Clock


class FacilityController:
    """Combina únicamente configuración y sensores; no consulta alertas ni actuadores."""

    def __init__(self, repositories: Repositories, clock: Clock) -> None:
        self._repositories = repositories
        self._clock = clock

    def status(self) -> FacilityStatus:
        config = self._repositories.config.load()
        sensors = self._repositories.sensors.list_all()
        health = FacilityAnalyzer.health(config, sensors, self._clock.now())
        return FacilityStatus(
            climate=FacilityAnalyzer.climate(config, health),
            store=FacilityAnalyzer.capacity(health, SensorType.PEOPLE_COUNTER, config.max_occupancy),
            parking=FacilityAnalyzer.capacity(health, SensorType.VEHICLE_COUNTER, config.parking_spaces),
            sensors=health,
            last_reading_at=FacilityAnalyzer.latest_update(sensors),
        )
