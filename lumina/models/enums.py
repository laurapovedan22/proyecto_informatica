"""Enumerados del dominio.

El *valor* de cada miembro es exactamente el texto que aparece en los ficheros JSON,
así que sirven a la vez de contrato de datos y de vocabulario del código.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    """Acciones que puede tener permitidas un rol (casos de uso del anteproyecto)."""

    VIEW_FACILITY = 'ver_establecimiento'
    VIEW_HISTORY = 'ver_historicos'
    SUPERVISE = 'supervisar'
    MANAGE_ALERTS = 'gestionar_alertas'
    CONTROL_ACTUATORS = 'controlar_actuadores'
    MANAGE_USERS = 'gestionar_usuarios'
    VIEW_ACTIVITY = 'ver_registros'
    CONFIGURE_SYSTEM = 'configurar_sistema'


class Role(StrEnum):
    """Perfiles de usuario de Lumina."""

    ADMIN = 'admin'
    SECURITY = 'seguridad'
    MANAGER = 'gerente'

    @property
    def label(self) -> str:
        """Nombre completo del perfil (``Personal de seguridad``)."""
        return _ROLE_LABELS[self]

    @property
    def short_label(self) -> str:
        """Nombre corto para títulos (``Dashboard · Seguridad``)."""
        return _ROLE_SHORT_LABELS[self]

    @property
    def permissions(self) -> frozenset[Permission]:
        return _ROLE_PERMISSIONS[self]

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


_ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: 'Administrador',
    Role.SECURITY: 'Personal de seguridad',
    Role.MANAGER: 'Gerente',
}

_ROLE_SHORT_LABELS: dict[Role, str] = {
    Role.ADMIN: 'Administración',
    Role.SECURITY: 'Seguridad',
    Role.MANAGER: 'Gerente',
}

# El gerente solo consulta; seguridad supervisa y actúa; el administrador lo puede todo.
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.MANAGER: frozenset({Permission.VIEW_FACILITY, Permission.VIEW_HISTORY}),
    Role.SECURITY: frozenset({
        Permission.VIEW_FACILITY,
        Permission.VIEW_HISTORY,
        Permission.SUPERVISE,
        Permission.MANAGE_ALERTS,
        Permission.CONTROL_ACTUATORS,
    }),
    Role.ADMIN: frozenset(Permission),
}


class SensorType(StrEnum):
    """Tipos de sensor del hexágono IoT."""

    TEMPERATURE = 'temperatura'
    HUMIDITY = 'humedad'
    MOTION = 'movimiento'
    DISTANCE = 'distancia'
    PEOPLE_COUNTER = 'contador_personas'
    VEHICLE_COUNTER = 'contador_vehiculos'

    @property
    def label(self) -> str:
        return _SENSOR_LABELS[self]

    @property
    def unit(self) -> str:
        return _SENSOR_UNITS[self]


_SENSOR_LABELS: dict[SensorType, str] = {
    SensorType.TEMPERATURE: 'Temperatura',
    SensorType.HUMIDITY: 'Humedad',
    SensorType.MOTION: 'Movimiento',
    SensorType.DISTANCE: 'Distancia',
    SensorType.PEOPLE_COUNTER: 'Contador de personas',
    SensorType.VEHICLE_COUNTER: 'Contador de vehículos',
}

_SENSOR_UNITS: dict[SensorType, str] = {
    SensorType.TEMPERATURE: '°C',
    SensorType.HUMIDITY: '%',
    SensorType.MOTION: '',
    SensorType.DISTANCE: 'cm',
    SensorType.PEOPLE_COUNTER: 'personas',
    SensorType.VEHICLE_COUNTER: 'coches',
}


class SensorStatus(StrEnum):
    """Estado operativo de un sensor o cámara."""

    ACTIVE = 'activo'
    ERROR = 'error'
    STALE = 'desactualizado'

    @property
    def label(self) -> str:
        return _SENSOR_STATUS_LABELS[self]


_SENSOR_STATUS_LABELS: dict[SensorStatus, str] = {
    SensorStatus.ACTIVE: 'Conectado',
    SensorStatus.ERROR: 'Error',
    SensorStatus.STALE: 'Desactualizado',
}


class ActuatorType(StrEnum):
    """Actuadores controlables desde la plataforma."""

    FAN = 'ventilador'
    LED = 'led'
    ALARM = 'alarma'

    @property
    def label(self) -> str:
        return _ACTUATOR_LABELS[self]


_ACTUATOR_LABELS: dict[ActuatorType, str] = {
    ActuatorType.FAN: 'Ventilador',
    ActuatorType.LED: 'LED de aviso',
    ActuatorType.ALARM: 'Alarma digital',
}


class ActuatorMode(StrEnum):
    """Quién decidió el estado actual del actuador."""

    AUTOMATIC = 'automatico'
    MANUAL = 'manual'


class AlertType(StrEnum):
    """Situaciones anómalas que generan una alerta."""

    RESTRICTED_MOTION = 'movimiento_zona_restringida'
    CRITICAL_TEMPERATURE = 'temperatura_critica'
    SENSOR_FAILURE = 'fallo_sensor'

    @property
    def label(self) -> str:
        return _ALERT_TYPE_LABELS[self]


_ALERT_TYPE_LABELS: dict[AlertType, str] = {
    AlertType.RESTRICTED_MOTION: 'Movimiento en zona restringida',
    AlertType.CRITICAL_TEMPERATURE: 'Temperatura crítica',
    AlertType.SENSOR_FAILURE: 'Fallo de sensor',
}


class AlertStatus(StrEnum):
    """Ciclo de vida de una alerta: pendiente → en revisión → resuelta."""

    PENDING = 'pendiente'
    IN_REVIEW = 'en_revision'
    RESOLVED = 'resuelta'

    @property
    def label(self) -> str:
        return _ALERT_STATUS_LABELS[self]

    @property
    def is_open(self) -> bool:
        return self is not AlertStatus.RESOLVED


_ALERT_STATUS_LABELS: dict[AlertStatus, str] = {
    AlertStatus.PENDING: 'Pendiente',
    AlertStatus.IN_REVIEW: 'En revisión',
    AlertStatus.RESOLVED: 'Resuelta',
}


class Metric(StrEnum):
    """Variables con histórico consultable."""

    OCCUPANCY = 'aforo'
    PARKING = 'parking'
    TEMPERATURE = 'temperatura'
    HUMIDITY = 'humedad'

    @property
    def label(self) -> str:
        return _METRIC_LABELS[self]

    @property
    def unit(self) -> str:
        return _METRIC_UNITS[self]


_METRIC_LABELS: dict[Metric, str] = {
    Metric.OCCUPANCY: 'Aforo del supermercado',
    Metric.PARKING: 'Ocupación del parking',
    Metric.TEMPERATURE: 'Temperatura',
    Metric.HUMIDITY: 'Humedad',
}

_METRIC_UNITS: dict[Metric, str] = {
    Metric.OCCUPANCY: 'personas',
    Metric.PARKING: 'coches',
    Metric.TEMPERATURE: '°C',
    Metric.HUMIDITY: '%',
}
