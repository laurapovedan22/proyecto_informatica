"""Entidades del dominio (H1.1: modelo de datos de Lumina).

Todas son *dataclasses* inmutables (``frozen``): para cambiar algo se crea una copia con
los métodos ``with_*``… y se guarda a través del repositorio. Así ninguna vista puede
modificar por accidente datos compartidos entre usuarios.

En el Sprint 1 solo los usuarios tienen comportamiento. El resto de entidades definen el
contrato de datos de sensores, cámaras, actuadores, alertas e históricos (ver
``docs/esquemas-json.md``) sobre el que se construirán los Sprints 2 a 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime

from .enums import (
    ActuatorMode,
    ActuatorType,
    AlertStatus,
    AlertType,
    Metric,
    Permission,
    Role,
    SensorStatus,
    SensorType,
)


@dataclass(frozen=True, slots=True)
class User:
    """Cuenta de acceso. ``role=None`` indica una solicitud pendiente de aprobación."""

    id: str
    name: str
    email: str
    password_hash: str = field(repr=False)
    role: Role | None = None
    active: bool = True
    connected: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def is_pending(self) -> bool:
        return self.role is None

    @property
    def can_sign_in(self) -> bool:
        return self.active and self.role is not None

    @property
    def role_label(self) -> str:
        return self.role.label if self.role is not None else 'Pendiente de aprobación'

    def can(self, permission: Permission) -> bool:
        return self.role is not None and self.role.can(permission)

    def signed_in(self, at: datetime) -> User:
        return replace(self, connected=True, last_login_at=at)

    def signed_out(self) -> User:
        return replace(self, connected=False)

    def with_role(self, role: Role) -> User:
        return replace(self, role=role)

    def with_active(self, active: bool) -> User:
        return replace(self, active=active, connected=self.connected and active)

    def with_profile(self, name: str, email: str) -> User:
        return replace(self, name=name, email=email)

    def with_password_hash(self, password_hash: str) -> User:
        return replace(self, password_hash=password_hash)


@dataclass(frozen=True, slots=True)
class Zone:
    """Zona supervisada del establecimiento (tienda, almacén, parking…)."""

    id: str
    name: str
    restricted: bool = False


@dataclass(frozen=True, slots=True)
class SystemConfig:
    """Parámetros del establecimiento (``configuracion.json``); se editarán en el Sprint 3."""

    facility_name: str = 'Supermercado Lumina'
    max_occupancy: int = 150
    parking_spaces: int = 50
    fan_threshold: float = 26.0
    """Temperatura (°C) a partir de la cual debe activarse el ventilador."""
    critical_temperature: float = 30.0
    """Temperatura (°C) que genera un aviso al personal de seguridad."""
    max_reading_age_minutes: int | None = None
    """Antigüedad máxima de una lectura antes de marcar el sensor como desactualizado."""
    main_zone_id: str = 'tienda'
    """Zona cuyas condiciones ambientales se muestran en los dashboards."""
    zones: tuple[Zone, ...] = ()


@dataclass(frozen=True, slots=True)
class Sensor:
    """Última lectura conocida de un sensor físico (o simulado)."""

    id: str
    name: str
    type: SensorType
    zone_id: str
    value: float | None = None
    """Valor numérico; en los sensores de movimiento 1 = detectado y 0 = sin movimiento."""
    status: SensorStatus = SensorStatus.ACTIVE
    updated_at: datetime | None = None

    @property
    def unit(self) -> str:
        return self.type.unit


@dataclass(frozen=True, slots=True)
class Camera:
    """Cámara de vigilancia. ``stream_url`` admite una imagen o un flujo MJPEG."""

    id: str
    name: str
    zone_id: str
    stream_url: str | None = None
    status: SensorStatus = SensorStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class Actuator:
    """Ventilador, LED de aviso o alarma digital."""

    id: str
    name: str
    type: ActuatorType
    zone_id: str
    is_on: bool = False
    mode: ActuatorMode = ActuatorMode.MANUAL
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Alert:
    """Incidencia detectada (movimiento en zona restringida, temperatura crítica…)."""

    id: str
    type: AlertType
    zone_id: str
    created_at: datetime
    status: AlertStatus = AlertStatus.PENDING
    description: str = ''
    sensor_id: str | None = None
    handled_by: str | None = None
    updated_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.status.is_open


@dataclass(frozen=True, slots=True)
class Reading:
    """Lectura histórica de una variable en un instante."""

    metric: Metric
    timestamp: datetime
    value: float
    sensor_status: SensorStatus = SensorStatus.ACTIVE

    @property
    def day(self) -> date:
        return self.timestamp.date()
