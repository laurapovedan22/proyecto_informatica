"""Bloques reutilizables de alertas y equipos (H3.2–H3.4)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import partial

from ...models import ActuatorMode, ActuatorType, AlertStatus, ZoneActuator, ZoneAlert
from ..formatting import Formatter
from ..theme import Theme
from .base import Box, Picture, Text
from .buttons import Button, ButtonVariant
from .layout import AlertBanner, DefinitionRow, Panel


class OpenAlertsBanner:
    """Aviso del dashboard con acceso al listado completo de supervisión."""

    def __init__(self, alerts: tuple[ZoneAlert, ...], on_review: Callable[[], object]) -> None:
        if alerts:
            AlertBanner(
                'Revisa las incidencias de seguridad del establecimiento.',
                emphasis=Formatter.plural(len(alerts), 'alerta pendiente', 'alertas pendientes'),
                action='Revisar alertas',
                on_action=on_review,
            )


class AlertList(Panel):
    """Detalle completo y acciones opcionales; sin acciones cuando solo se consulta."""

    def __init__(
        self,
        alerts: tuple[ZoneAlert, ...],
        today: date,
        on_status: Callable[[str, AlertStatus], object] | None = None,
    ) -> None:
        super().__init__('Alertas')
        with self:
            if not alerts:
                Text('No hay alertas registradas.', tag='p', classes=Theme.MUTED)
            for item in alerts:
                alert = item.alert
                row = DefinitionRow().mark(f'alert-{alert.id}')
                with row.leading:
                    Text(alert.type.label, tag='strong', classes=Theme.STRONG)
                    Text(
                        f'{item.zone.name} · {Formatter.moment(alert.created_at, today)} · {alert.status.label}',
                        tag='p',
                        classes=Theme.SMALL,
                    )
                    Text(alert.description, tag='p', classes=Theme.MUTED)
                    Text(f'Sensor: {alert.sensor_id or "Sin sensor"}', tag='p', classes=Theme.SMALL)
                    capture = Formatter.capture_url(alert.capture)
                    if capture is not None:  # la imagen en la que YOLO vio a la persona
                        Picture(
                            capture, alt=f'Imagen de la alerta: {alert.description}', classes=Theme.ALERT_CAPTURE
                        ).mark(f'capture-{alert.id}')
                    if alert.handled_by:
                        Text(
                            f'Atendida por {alert.handled_by} · {Formatter.moment(alert.updated_at, today)}',
                            tag='p',
                            classes=Theme.SMALL,
                        )
                if alert.is_open and on_status is not None:
                    with row.trailing, Box(Theme.BUTTON_ROW):
                        if alert.status is AlertStatus.PENDING:
                            Button('En revisión', on_click=partial(on_status, alert.id, AlertStatus.IN_REVIEW)).mark(
                                f'review-{alert.id}'
                            )
                        Button(
                            'Marcar resuelta',
                            variant=ButtonVariant.PRIMARY,
                            on_click=partial(on_status, alert.id, AlertStatus.RESOLVED),
                        ).mark(f'resolve-{alert.id}')


class EquipmentPanel(Panel):
    """Estado de los actuadores y control manual o retorno del ventilador a automático."""

    def __init__(
        self,
        actuators: tuple[ZoneActuator, ...],
        *,
        on_switch: Callable[[str, bool], object] | None = None,
        on_automatic: Callable[[str], object] | None = None,
    ) -> None:
        super().__init__('Control de equipos' if on_switch else 'Estado de los equipos')
        with self:
            if not actuators:
                Text('No hay equipos configurados.', tag='p', classes=Theme.MUTED)
            for item in actuators:
                actuator = item.actuator
                row = DefinitionRow().mark(f'equipment-{actuator.id}')
                with row.leading:
                    state = 'Encendido' if actuator.is_on else 'Apagado'
                    mode = 'automático' if actuator.mode is ActuatorMode.AUTOMATIC else 'manual'
                    Text(f'{actuator.name} · {state} · Modo {mode}', tag='p')
                    Text(f'Zona: {item.zone.name}', classes=Theme.SMALL)
                if on_switch is not None:
                    with row.trailing, Box(Theme.BUTTON_ROW):
                        action = 'Apagar' if actuator.is_on else 'Encender'
                        Button(action, on_click=partial(on_switch, actuator.id, not actuator.is_on)).mark(
                            f'actuator-{actuator.id}'
                        )
                        if (
                            actuator.type is ActuatorType.FAN
                            and actuator.mode is ActuatorMode.MANUAL
                            and on_automatic is not None
                        ):
                            Button('Volver a automático', on_click=partial(on_automatic, actuator.id)).mark(
                                f'automatic-{actuator.id}'
                            )
