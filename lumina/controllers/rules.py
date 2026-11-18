"""Reglas de seguridad y ventilación de H3.1–H3.3, independientes de la interfaz.

Las personas que ve YOLO en las cámaras (ampliación del 18/11/2026) cuentan como el movimiento:
en una zona restringida abren una alerta con la imagen y encienden el LED y la alarma de la zona.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from ..models import (
    Actuator,
    ActuatorMode,
    ActuatorType,
    Alert,
    AlertType,
    Camera,
    SensorState,
    SensorStatus,
    SensorType,
    SystemConfig,
)
from ..repositories import DuplicateError, Repositories
from .analysis import FacilityAnalyzer
from .clock import Clock
from .security import IdGenerator


@dataclass(frozen=True, slots=True)
class RulesResult:
    """Solo las altas de alertas y los cambios de equipos confirmados en esta evaluación."""

    alerts_created: tuple[Alert, ...] = ()
    actuators_changed: tuple[Actuator, ...] = ()


class RulesController:
    """Relee la configuración en cada ciclo y escribe con comprobaciones atómicas.

    Histéresis del ventilador: enciende por encima del umbral y apaga al llegar a
    umbral − 0,5 °C. Dentro de la banda mantiene el estado. Sin lectura válida lo conserva.
    Una cámara cuyo último análisis ve personas en una zona restringida actúa como un sensor de
    movimiento de esa zona: alerta (con la imagen) y LED y alarma encendidos.
    """

    HYSTERESIS = 0.5

    def __init__(self, repositories: Repositories, clock: Clock) -> None:
        self._repositories = repositories
        self._clock = clock
        self._lock = RLock()

    def evaluate(self) -> RulesResult:
        """Evalúa el estado actual; las alertas resueltas permiten crear una nueva incidencia."""
        with self._lock:
            config = self._repositories.config.modify(lambda current: current)
            now = self._clock.now()
            health = FacilityAnalyzer.health(config, self._repositories.sensors.list_all(), now)
            alerts: list[Alert] = []
            temperatures: dict[str, float] = {}
            motion_zones: set[str] = set()
            for item in health:
                sensor = item.sensor
                alert_type: AlertType | None = None
                if sensor.status is SensorStatus.ERROR or item.state is SensorState.ERROR:
                    alert_type = AlertType.SENSOR_FAILURE
                elif item.state is SensorState.ACTIVE and sensor.value is not None:
                    if sensor.type is SensorType.TEMPERATURE:
                        temperatures[sensor.zone_id] = max(temperatures.get(sensor.zone_id, sensor.value), sensor.value)
                        if sensor.value >= config.critical_temperature:
                            alert_type = AlertType.CRITICAL_TEMPERATURE
                    elif sensor.type is SensorType.MOTION and sensor.value > 0 and item.zone.restricted:
                        motion_zones.add(sensor.zone_id)
                        alert_type = AlertType.RESTRICTED_MOTION
                if alert_type is not None:
                    description = f'{alert_type.label}: {sensor.name}'
                    created = self._create_alert(alert_type, sensor.id, sensor.zone_id, description)
                    if created is not None:
                        alerts.append(created)
            for camera in self._repositories.cameras.list_all():
                zone = FacilityAnalyzer.zone(config, camera.zone_id)
                if zone.restricted and FacilityAnalyzer.camera_sees_people(camera, now, config.max_reading_age_minutes):
                    motion_zones.add(camera.zone_id)
                    created = self._create_alert(
                        AlertType.PERSON_IN_RESTRICTED_ZONE, camera.id, camera.zone_id, self._describe(camera),
                        capture=camera.capture,
                    )
                    if created is not None:
                        alerts.append(created)
            changed: list[Actuator] = []
            for actuator in self._repositories.actuators.list_all():

                def change(current: Actuator) -> Actuator:
                    updated = self._automatic(current, temperatures, motion_zones, config)
                    if updated is not current:
                        changed.append(updated)
                    return updated

                self._repositories.actuators.modify(actuator.id, change)
            return RulesResult(tuple(alerts), tuple(changed))

    @staticmethod
    def _describe(camera: Camera) -> str:
        people = camera.people or 0
        seen = '1 persona detectada' if people == 1 else f'{people} personas detectadas'
        return f'{AlertType.PERSON_IN_RESTRICTED_ZONE.label}: {camera.name} ({seen} por YOLO)'

    def _create_alert(
        self, alert_type: AlertType, source_id: str, zone_id: str, description: str, *, capture: str | None = None,
    ) -> Alert | None:
        """Alerta nueva del sensor o cámara ``source_id``, salvo que ya tenga una abierta de ese tipo."""
        alert = Alert(
            id=IdGenerator.new('alr'),
            type=alert_type,
            zone_id=zone_id,
            sensor_id=source_id,
            created_at=self._clock.now(),
            description=description,
            capture=capture,
        )

        def check(current: list[Alert]) -> None:
            if any(
                item.is_open
                and (item.type, item.zone_id, item.sensor_id) == (alert.type, alert.zone_id, alert.sensor_id)
                for item in current
            ):
                raise DuplicateError('Ya existe una alerta abierta para esta regla y sensor.')

        try:
            self._repositories.alerts.add(alert, check=check)
        except DuplicateError:
            return None
        return alert

    def _automatic(
        self,
        actuator: Actuator,
        temperatures: dict[str, float],
        motion_zones: set[str],
        config: SystemConfig,
    ) -> Actuator:
        on = actuator.is_on
        if actuator.type is ActuatorType.FAN:
            if actuator.mode is ActuatorMode.MANUAL or actuator.zone_id not in temperatures:
                return actuator
            temperature = temperatures[actuator.zone_id]
            if temperature > config.fan_threshold:
                on = True
            elif temperature <= config.fan_threshold - self.HYSTERESIS:
                on = False
        elif actuator.zone_id in motion_zones:
            on = True
        else:
            return actuator
        if (on, ActuatorMode.AUTOMATIC) == (actuator.is_on, actuator.mode):
            return actuator
        return replace(actuator, is_on=on, mode=ActuatorMode.AUTOMATIC, updated_at=self._clock.now())
