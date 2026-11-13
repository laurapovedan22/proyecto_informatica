"""Indicadores y listas de sensores compartidos por dashboard y supervisión."""

from __future__ import annotations

from datetime import date

from ...models import CapacityStatus, FacilityStatus, SensorHealth, SensorState, ZoneMotion
from ..formatting import Formatter
from ..theme import Theme
from .base import StatusText, Text
from .data import DataTable, ProgressMeter
from .layout import DefinitionRow, MetricCard, MetricGrid, Note, Panel, TwoColumns


class FacilityMetrics(MetricGrid):
    """Aforo, plazas y ambiente con unidades e instante propio de cada indicador."""

    def __init__(self, status: FacilityStatus, today: date) -> None:
        super().__init__(columns=4)
        climate = status.climate
        with self:
            MetricCard(
                'Temperatura',
                Formatter.measurement(climate.temperature, '°C'),
                f'{climate.zone.name} · {Formatter.moment(climate.temperature_at, today)}',
            )
            MetricCard(
                'Humedad',
                Formatter.measurement(climate.humidity, '%'),
                f'{climate.zone.name} · {Formatter.moment(climate.humidity_at, today)}',
            )
            MetricCard(
                'Aforo tienda',
                f'{status.store.occupied} / {status.store.capacity} personas',
                f'Última lectura: {Formatter.moment(status.store.updated_at, today)}',
            )
            MetricCard(
                'Parking',
                f'{status.parking.available} plazas libres',
                f'{status.parking.occupied} de {status.parking.capacity} ocupadas · '
                f'{Formatter.moment(status.parking.updated_at, today)}',
            )


class OccupancyPanels(TwoColumns):
    """Aforo y aparcamiento con barras accesibles como en el mockup."""

    def __init__(self, status: FacilityStatus) -> None:
        super().__init__()
        with self:
            self._panel(
                'Aforo del supermercado',
                status.store,
                f'{status.store.occupied} personas',
                f'de {status.store.capacity} permitidas',
                f'{status.store.available} personas hasta completar el aforo',
            )
            self._panel(
                'Ocupación del parking',
                status.parking,
                f'{status.parking.occupied} plazas ocupadas',
                f'de {status.parking.capacity}',
                Formatter.plural(status.parking.available, 'plaza libre', 'plazas libres'),
            )

    @staticmethod
    def _panel(title: str, capacity: CapacityStatus, headline: str, detail: str, footnote: str) -> None:
        with Panel(title):
            Text(headline, tag='strong', classes=Theme.OCCUPANCY_VALUE)
            Text(detail, classes=Theme.MUTED)
            ProgressMeter(capacity.occupied, capacity.capacity, label=title)
            Text(footnote, classes=f'{Theme.SMALL} {Theme.MUTED}')


class SensorSummary(Panel):
    """Resumen de la salud de todos los sensores para seguridad y administración."""

    def __init__(self, sensors: tuple[SensorHealth, ...]) -> None:
        super().__init__('Estado de los sensores')
        with self:
            for state in SensorState:
                count = sum(item.state is state for item in sensors)
                DefinitionRow(
                    state.value, Formatter.plural(count, 'sensor', 'sensores'), tone=Formatter.sensor_tone(state)
                )
            if not sensors:
                Note('No hay sensores configurados.')


class SensorTable(Panel):
    """Lectura original, unidad, zona, estado y última actualización de cada sensor."""

    def __init__(self, sensors: tuple[SensorHealth, ...], today: date) -> None:
        super().__init__('Sensores')
        with self:
            if not sensors:
                Note('No hay sensores configurados.')
                return
            table = DataTable(('Sensor', 'Zona', 'Valor y unidad', 'Estado', 'Última actualización'))
            for item in sensors:
                row = table.row().mark(f'sensor-{item.sensor.id}')
                row.text(item.sensor.name)
                row.text(item.zone.name)
                row.text(Formatter.sensor_value(item.sensor))
                with row.cell():
                    StatusText(item.state.value, tone=Formatter.sensor_tone(item.state))
                row.text(Formatter.moment(item.sensor.updated_at, today))


class MotionTable(Panel):
    """Detecciones por zona y sensores que aportan la lectura."""

    def __init__(self, zones: tuple[ZoneMotion, ...], today: date) -> None:
        super().__init__('Detección de movimiento por zona')
        with self:
            if not zones:
                Note('No hay zonas configuradas.')
                return
            table = DataTable(('Zona', 'Estado', 'Sensores de movimiento', 'Última actualización'))
            for motion in zones:
                table.add_row(
                    motion.zone.name,
                    motion.label,
                    ', '.join(item.sensor.name for item in motion.sensors) or 'Sin sensor de movimiento',
                    Formatter.moment(motion.updated_at, today),
                ).mark(f'motion-{motion.zone.id}')
