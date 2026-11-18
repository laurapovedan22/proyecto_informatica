"""Reglas puras del Sprint 2: vigencia, ambiente, ocupación y movimiento (y personas vistas por YOLO)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from math import isfinite

from ..models import (
    Camera,
    CapacityStatus,
    ClimateStatus,
    Sensor,
    SensorHealth,
    SensorState,
    SensorStatus,
    SensorType,
    SystemConfig,
    Zone,
    ZoneMotion,
)


class FacilityAnalyzer:
    """Transforma lecturas en datos de presentación sin acceder a ficheros ni a NiceGUI."""

    @staticmethod
    def zone(config: SystemConfig, zone_id: str) -> Zone:
        """Conserva el identificador si aún no hay un nombre de zona configurado."""
        return next((zone for zone in config.zones if zone.id == zone_id), Zone(zone_id, zone_id))

    @staticmethod
    def sensor_state(sensor: Sensor, now: datetime, max_age_minutes: int | None) -> SensorState:
        """Sin lectura prevalece; después valor no finito, error y desactualización.

        Con vigencia habilitada, una lectura sin fecha tampoco puede considerarse actual.
        La igualdad con el límite sigue vigente: solo caduca al superarlo.
        """
        if sensor.value is None:
            return SensorState.NO_DATA
        if not isfinite(sensor.value) or sensor.status is SensorStatus.ERROR:
            return SensorState.ERROR
        if sensor.status is SensorStatus.STALE:
            return SensorState.STALE
        if max_age_minutes and (
            sensor.updated_at is None or now - sensor.updated_at > timedelta(minutes=max_age_minutes)
        ):
            return SensorState.STALE
        return SensorState.ACTIVE

    @staticmethod
    def camera_sees_people(camera: Camera, now: datetime, max_age_minutes: int | None) -> bool:
        """El último análisis de YOLO vio a alguien y vale: cámara activa y, si hay vigencia, no caducado.

        Es la misma regla de vigencia que la de las lecturas de los sensores.
        """
        if camera.status is not SensorStatus.ACTIVE or camera.people is None or camera.people <= 0:
            return False
        return not max_age_minutes or (
            camera.analyzed_at is not None and now - camera.analyzed_at <= timedelta(minutes=max_age_minutes)
        )

    @classmethod
    def health(cls, config: SystemConfig, sensors: Sequence[Sensor], now: datetime) -> tuple[SensorHealth, ...]:
        return tuple(
            SensorHealth(
                sensor, cls.zone(config, sensor.zone_id), cls.sensor_state(sensor, now, config.max_reading_age_minutes)
            )
            for sensor in sensors
        )

    @staticmethod
    def latest_update(sensors: Iterable[Sensor]) -> datetime | None:
        return max((sensor.updated_at for sensor in sensors if sensor.updated_at is not None), default=None)

    @staticmethod
    def reading_time(items: Sequence[SensorHealth]) -> datetime | None:
        """Instante más antiguo de los contribuyentes; no oculta una lectura anterior."""
        if not items or any(item.sensor.updated_at is None for item in items):
            return None
        return min(item.sensor.updated_at for item in items if item.sensor.updated_at is not None)

    @classmethod
    def capacity(cls, health: Sequence[SensorHealth], sensor_type: SensorType, capacity: int) -> CapacityStatus:
        """Suma neta, redondeada a enteros y acotada; no modifica las lecturas originales."""
        items = [item for item in health if item.sensor.type is sensor_type and item.state is SensorState.ACTIVE]
        total = round(sum(item.sensor.value for item in items if item.sensor.value is not None))
        limit = max(capacity, 0)
        return CapacityStatus(min(max(total, 0), limit), limit, cls.reading_time(items))

    @classmethod
    def climate(cls, config: SystemConfig, health: Sequence[SensorHealth]) -> ClimateStatus:
        """Medias de la zona principal; nunca sustituye una zona por otra silenciosamente."""
        temperature, temperature_at = cls._average(health, SensorType.TEMPERATURE, config.main_zone_id)
        humidity, humidity_at = cls._average(health, SensorType.HUMIDITY, config.main_zone_id)
        return ClimateStatus(cls.zone(config, config.main_zone_id), temperature, humidity, temperature_at, humidity_at)

    @classmethod
    def _average(
        cls,
        health: Sequence[SensorHealth],
        sensor_type: SensorType,
        zone_id: str,
    ) -> tuple[float | None, datetime | None]:
        items = [
            item
            for item in health
            if item.sensor.type is sensor_type and item.sensor.zone_id == zone_id and item.state is SensorState.ACTIVE
        ]
        values = [item.sensor.value for item in items if item.sensor.value is not None]
        return (round(sum(values) / len(values), 1) if values else None, cls.reading_time(items))

    @classmethod
    def motion(cls, zone: Zone, health: Sequence[SensorHealth]) -> ZoneMotion:
        items = tuple(item for item in health if item.sensor.type is SensorType.MOTION and item.zone.id == zone.id)
        active = [item for item in items if item.state is SensorState.ACTIVE]
        if active:
            detected = any(item.sensor.value is not None and item.sensor.value > 0 for item in active)
            return ZoneMotion(zone, items, detected, SensorState.ACTIVE, cls.reading_time(active))
        state = next(
            (state for state in (SensorState.ERROR, SensorState.STALE) if any(item.state is state for item in items)),
            SensorState.NO_DATA,
        )
        return ZoneMotion(zone, items, None, state, cls.latest_update(item.sensor for item in items))
