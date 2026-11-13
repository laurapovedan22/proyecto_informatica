"""Consulta de cámaras, detecciones y sensores (H2.1 y H2.4)."""

from __future__ import annotations

from ..models import CameraFeed, SupervisionSnapshot
from ..repositories import Repositories
from .analysis import FacilityAnalyzer
from .clock import Clock


class SupervisionController:
    """Construye la instantánea que muestra la página protegida por SUPERVISE."""

    def __init__(self, repositories: Repositories, clock: Clock) -> None:
        self._repositories = repositories
        self._clock = clock

    def snapshot(self) -> SupervisionSnapshot:
        config = self._repositories.config.load()
        sensors = self._repositories.sensors.list_all()
        cameras = self._repositories.cameras.list_all()
        health = FacilityAnalyzer.health(config, sensors, self._clock.now())
        zone_ids = dict.fromkeys(
            [zone.id for zone in config.zones]
            + [sensor.zone_id for sensor in sensors]
            + [camera.zone_id for camera in cameras]
        )
        motion = {
            zone_id: FacilityAnalyzer.motion(FacilityAnalyzer.zone(config, zone_id), health) for zone_id in zone_ids
        }
        return SupervisionSnapshot(
            cameras=tuple(
                CameraFeed(camera, motion[camera.zone_id].zone, motion[camera.zone_id]) for camera in cameras
            ),
            zones=tuple(motion.values()),
            sensors=health,
            last_reading_at=FacilityAnalyzer.latest_update(sensors),
        )
