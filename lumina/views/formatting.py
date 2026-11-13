"""Formato en español de números y fechas para la interfaz."""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite

from ..models import Sensor, SensorState, SensorType
from .theme import ToneName


class Formatter:
    """Convierte valores del modelo en textos como «14:25», «13/10/2026 18:40» o «3 usuarios»."""

    EMPTY = '—'

    @staticmethod
    def number(value: float) -> str:
        return f'{value:g}'.replace('.', ',')

    @classmethod
    def measurement(cls, value: float | None, unit: str) -> str:
        if value is None:
            return f'Sin datos · {unit}' if unit else 'Sin datos'
        return f'{cls.number(value)} {unit}'.strip()

    @classmethod
    def sensor_value(cls, sensor: Sensor) -> str:
        if sensor.value is None:
            return cls.measurement(None, sensor.unit)
        if not isfinite(sensor.value):
            return f'Lectura inválida · {sensor.unit}' if sensor.unit else 'Lectura inválida'
        if sensor.type is SensorType.MOTION:
            return 'Presencia' if sensor.value > 0 else 'Sin presencia'
        return cls.measurement(sensor.value, sensor.unit)

    @staticmethod
    def sensor_tone(state: SensorState) -> ToneName:
        if state is SensorState.ACTIVE:
            return ToneName.POSITIVE
        if state is SensorState.ERROR:
            return ToneName.DANGER
        return ToneName.MUTED if state is SensorState.NO_DATA else ToneName.WARNING

    @classmethod
    def clock(cls, moment: datetime | None) -> str:
        """Hora sin cero inicial, como en el mockup: ``9:00``, ``14:25``."""
        return cls.EMPTY if moment is None else f'{moment.hour}:{moment.minute:02d}'

    @classmethod
    def moment(cls, moment: datetime | None, today: date) -> str:
        """``Hoy · 14:25`` si es de hoy; si no, fecha y hora."""
        if moment is None:
            return cls.EMPTY
        if moment.date() == today:
            return f'Hoy · {cls.clock(moment)}'
        return f'{cls.short_date(moment.date())} {cls.clock(moment)}'

    @staticmethod
    def short_date(day: date) -> str:
        return day.strftime('%d/%m/%Y')

    @staticmethod
    def camera_time(moment: datetime) -> str:
        """Fecha y hora con segundos sobreimpresas en el vídeo de una cámara: ``04/11/2026 17:05:09``."""
        return moment.strftime('%d/%m/%Y %H:%M:%S')

    @staticmethod
    def plural(count: int, singular: str, plural: str) -> str:
        return f'{count} {singular if count == 1 else plural}'
