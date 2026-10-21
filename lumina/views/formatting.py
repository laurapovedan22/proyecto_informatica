"""Formato en español de números y fechas para la interfaz."""

from __future__ import annotations

from datetime import date, datetime


class Formatter:
    """Convierte valores del modelo en textos como «14:25», «13/10/2026 18:40» o «3 usuarios»."""

    EMPTY = '—'

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
    def plural(count: int, singular: str, plural: str) -> str:
        return f'{count} {singular if count == 1 else plural}'
