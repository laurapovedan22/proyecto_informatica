"""Variables virtuales inmutables de cuentas y supervisión (Sprints 1 y 2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .entities import Camera, Sensor, Zone


class SensorState(StrEnum):
    """Estado calculado de una lectura; no cambia el contrato JSON del sensor."""

    ACTIVE = 'Activo'
    ERROR = 'Error'
    STALE = 'Desactualizado'
    NO_DATA = 'Sin datos'


@dataclass(frozen=True, slots=True)
class CapacityStatus:
    """Ocupación ya acotada por el controlador entre cero y la capacidad."""

    occupied: int
    capacity: int
    updated_at: datetime | None

    @property
    def available(self) -> int:
        return self.capacity - self.occupied

    @property
    def ratio(self) -> float:
        return self.occupied / self.capacity if self.capacity > 0 else 0.0


@dataclass(frozen=True, slots=True)
class ClimateStatus:
    """Media de lecturas operativas de la zona principal y sus instantes de lectura."""

    zone: Zone
    temperature: float | None
    humidity: float | None
    temperature_at: datetime | None
    humidity_at: datetime | None


@dataclass(frozen=True, slots=True)
class SensorHealth:
    """Sensor, zona y estado efectivo calculado por el controlador."""

    sensor: Sensor
    zone: Zone
    state: SensorState


@dataclass(frozen=True, slots=True)
class ZoneMotion:
    """Detección agregada de los sensores operativos de una zona."""

    zone: Zone
    sensors: tuple[SensorHealth, ...]
    detected: bool | None
    state: SensorState
    updated_at: datetime | None

    @property
    def label(self) -> str:
        if self.detected is None:
            return self.state.value
        return 'Movimiento detectado' if self.detected else 'Sin movimiento'


@dataclass(frozen=True, slots=True)
class CameraFeed:
    """Señal de cámara junto con la detección de su zona (sin alertas)."""

    camera: Camera
    zone: Zone
    motion: ZoneMotion


@dataclass(frozen=True, slots=True)
class FacilityStatus:
    """Datos del establecimiento comunes a todos los dashboards."""

    climate: ClimateStatus
    store: CapacityStatus
    parking: CapacityStatus
    sensors: tuple[SensorHealth, ...]
    last_reading_at: datetime | None


@dataclass(frozen=True, slots=True)
class SupervisionSnapshot:
    """Lecturas, cámaras y movimiento para la pantalla de supervisión."""

    cameras: tuple[CameraFeed, ...]
    zones: tuple[ZoneMotion, ...]
    sensors: tuple[SensorHealth, ...]
    last_reading_at: datetime | None


@dataclass(frozen=True, slots=True)
class UserCounts:
    """Contadores del panel de administración."""

    total: int
    connected: int
    pending: int
    inactive: int = 0
    locked: int = 0
