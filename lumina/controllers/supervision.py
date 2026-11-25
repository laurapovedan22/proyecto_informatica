"""Cámaras, sensores, alertas y control de equipos (H2.1, H2.4, H3.2–H3.4)."""

from __future__ import annotations

from dataclasses import replace

from ..models import (
    Actuator,
    ActuatorMode,
    ActuatorType,
    Alert,
    AlertStatus,
    CameraFeed,
    Permission,
    SupervisionSnapshot,
    User,
    ZoneActuator,
    ZoneAlert,
)
from ..repositories import Repositories
from .analysis import FacilityAnalyzer
from .authorization import require_actor
from .clock import Clock
from .errors import NotFoundError, PermissionDeniedError, ValidationError
from .rules import RulesController


class SupervisionController:
    """Construye la instantánea que muestra la página protegida por SUPERVISE."""

    def __init__(self, repositories: Repositories, clock: Clock, rules: RulesController) -> None:
        self._repositories = repositories
        self._clock = clock
        self._rules = rules

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
            alerts=self.alerts(),
            actuators=self.equipment(),
            last_reading_at=FacilityAnalyzer.latest_update(sensors),
        )

    def equipment(self) -> tuple[ZoneActuator, ...]:
        """Estados consultables también por gerencia, sin acciones de control, con el nombre de su zona."""
        config = self._repositories.config.load()
        return tuple(
            ZoneActuator(actuator, FacilityAnalyzer.zone(config, actuator.zone_id))
            for actuator in self._repositories.actuators.list_all()
        )

    def alerts(self) -> tuple[ZoneAlert, ...]:
        """Listado completo con zona; las fechas y el responsable se conservan en cada alerta."""
        config = self._repositories.config.load()
        alerts = sorted(self._repositories.alerts.list_all(), key=lambda item: item.created_at, reverse=True)
        return tuple(ZoneAlert(alert, FacilityAnalyzer.zone(config, alert.zone_id)) for alert in alerts)

    def open_alerts(self) -> tuple[ZoneAlert, ...]:
        return tuple(item for item in self.alerts() if item.alert.is_open)

    def update_alert(self, alert_id: str, status: AlertStatus, actor: User) -> Alert:
        """Revisión o resolución atómica con el usuario vigente como responsable (H3.4)."""
        PermissionDeniedError.require(actor, Permission.MANAGE_ALERTS)
        if status not in (AlertStatus.IN_REVIEW, AlertStatus.RESOLVED):
            raise ValidationError('Solo se puede marcar En revisión o Resuelta.')

        def change(current: Alert) -> Alert:
            responsible = require_actor(self._repositories.users, actor, Permission.MANAGE_ALERTS)
            if current.status is status:
                return current
            if not current.is_open:
                raise ValidationError('La alerta ya está resuelta.')
            return replace(current, status=status, handled_by=responsible.name, updated_at=self._clock.now())

        updated = self._repositories.alerts.modify(alert_id, change)
        if updated is None:
            raise NotFoundError('La alerta ya no existe.')
        return updated

    def set_actuator(self, actuator_id: str, on: bool, actor: User) -> Actuator:
        """Un control manual fija el estado y pasa a modo manual, aunque ya tuviera ese estado."""
        return self._change_actuator(actuator_id, actor, on=on, mode=ActuatorMode.MANUAL)

    def set_automatic(self, actuator_id: str, actor: User) -> Actuator:
        """Devuelve un ventilador al control automático y evalúa inmediatamente las reglas."""
        updated = self._change_actuator(actuator_id, actor, on=None, mode=ActuatorMode.AUTOMATIC)
        self._rules.evaluate()
        return self._repositories.actuators.get(updated.id) or updated

    def _change_actuator(
        self, actuator_id: str, actor: User, *, on: bool | None, mode: ActuatorMode,
    ) -> Actuator:
        PermissionDeniedError.require(actor, Permission.CONTROL_ACTUATORS)

        def change(current: Actuator) -> Actuator:
            require_actor(self._repositories.users, actor, Permission.CONTROL_ACTUATORS)
            if mode is ActuatorMode.AUTOMATIC and current.type is not ActuatorType.FAN:
                raise ValidationError('Solo los ventiladores ofrecen volver a automático.')
            state = current.is_on if on is None else on
            if (current.is_on, current.mode) == (state, mode):
                return current
            return replace(current, is_on=state, mode=mode, updated_at=self._clock.now())

        updated = self._repositories.actuators.modify(actuator_id, change)
        if updated is None:
            raise NotFoundError('El equipo ya no existe.')
        return updated
