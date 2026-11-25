"""Umbrales, capacidad y zonas restringidas (H3.1 / RF-08)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..models import Permission, SystemConfig, User
from ..repositories import Repositories
from .authorization import require_actor
from .errors import PermissionDeniedError, ValidationError
from .rules import RulesController


@dataclass(frozen=True, slots=True)
class ConfigurationChanges:
    """Valores editables por administración; el resto del documento se conserva."""

    fan_threshold: float
    critical_temperature: float
    max_occupancy: int
    parking_spaces: int
    max_reading_age_minutes: int | None
    restricted_zone_ids: frozenset[str]


class ConfigurationController:
    """Valida y guarda de forma atómica; evalúa las reglas tras confirmar el cambio."""

    def __init__(self, repositories: Repositories, rules: RulesController) -> None:
        self._repositories = repositories
        self._rules = rules

    def current(self) -> SystemConfig:
        return self._repositories.config.load()

    def update(self, changes: ConfigurationChanges, actor: User) -> SystemConfig:
        PermissionDeniedError.require(actor, Permission.CONFIGURE_SYSTEM)
        self._validate(changes)

        def change(current: SystemConfig) -> SystemConfig:
            require_actor(self._repositories.users, actor, Permission.CONFIGURE_SYSTEM)
            if changes.restricted_zone_ids - {zone.id for zone in current.zones}:
                raise ValidationError('Alguna de las zonas ya no existe. Vuelve a cargar la configuración.')
            return replace(
                current,
                fan_threshold=round(changes.fan_threshold, 1),
                critical_temperature=round(changes.critical_temperature, 1),
                max_occupancy=changes.max_occupancy,
                parking_spaces=changes.parking_spaces,
                max_reading_age_minutes=changes.max_reading_age_minutes or None,
                zones=tuple(replace(zone, restricted=zone.id in changes.restricted_zone_ids) for zone in current.zones),
            )

        updated = self._repositories.config.modify(change)
        self._rules.evaluate()
        return updated

    @staticmethod
    def _validate(changes: ConfigurationChanges) -> None:
        for value in (changes.fan_threshold, changes.critical_temperature):
            if not math.isfinite(value) or not -10 <= value <= 60:
                raise ValidationError('Las temperaturas deben estar entre -10 y 60 °C y ser finitas.')
        if round(changes.critical_temperature, 1) <= round(changes.fan_threshold, 1):
            raise ValidationError('La temperatura crítica debe ser mayor que el umbral del ventilador.')
        for value, maximum in ((changes.max_occupancy, 10_000), (changes.parking_spaces, 5_000)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValidationError('El aforo y las plazas deben ser enteros positivos dentro de los límites.')
        age = changes.max_reading_age_minutes
        if age is not None and (type(age) is not int or not 0 <= age <= 1440):
            raise ValidationError('La antigüedad máxima debe ser un entero entre 0 y 1440 minutos.')
