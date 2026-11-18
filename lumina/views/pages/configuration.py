"""Configuración del establecimiento: umbrales, capacidad y zonas restringidas (H3.1 / RF-08)."""

from __future__ import annotations

from nicegui import ui

from ...controllers import ConfigurationChanges
from ...models import Permission
from ..components import Box, Button, ButtonVariant, DefinitionRow, NumberField, PageHeader, Panel, Text, TwoColumns
from ..routes import Route
from ..theme import Theme
from .base import ProtectedPage


class ConfigurationPage(ProtectedPage):
    """Formulario del administrador para los parámetros que usan las reglas de alerta."""

    route = Route.CONFIGURATION
    title = 'Configuración'
    permission = Permission.CONFIGURE_SYSTEM

    def render(self) -> None:
        self._dirty = False
        self._edit_revision = 0
        self._config = self.live(self.services.configuration.current, self._refresh_form)
        self._form()

    def _refresh_form(self) -> None:
        """Los cambios externos y el cambio de día no descartan la edición en curso."""
        if not self._dirty:
            self._form.refresh()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._edit_revision += 1

    @ui.refreshable_method
    def _form(self) -> None:
        config = self._config.value
        if config is None:  # no se pudo leer: LiveData avisa y reintenta hasta que el fichero vuelva a estar bien
            PageHeader('Configuración', 'Umbrales de alerta, capacidad y zonas restringidas')
            return
        PageHeader('Configuración', f'Umbrales de alerta, capacidad y zonas restringidas · {config.facility_name}')
        with TwoColumns():
            with Panel('Umbrales de temperatura'), Box(Theme.FORM):
                self._fan_threshold = NumberField(
                    'Umbral del ventilador (se activa al superarlo)',
                    value=config.fan_threshold,
                    minimum=-10,
                    maximum=60,
                    step=0.5,
                    precision=1,
                    suffix='°C',
                )
                self._critical = NumberField(
                    'Avisar a seguridad a partir de',
                    value=config.critical_temperature,
                    minimum=-10,
                    maximum=60,
                    step=0.5,
                    precision=1,
                    suffix='°C',
                )
                self._max_age = NumberField(
                    'Marcar un sensor como desactualizado tras',
                    value=config.max_reading_age_minutes or 0,
                    minimum=0,
                    maximum=1440,
                    step=1,
                    precision=0,
                    suffix='min',
                )
                Text(
                    'Con 0 no se comprueba la antigüedad de las lecturas.',
                    tag='p',
                    classes=f'{Theme.SMALL} {Theme.MUTED}',
                )
            with Panel('Capacidad'), Box(Theme.FORM):
                self._max_occupancy = NumberField(
                    'Aforo máximo del supermercado',
                    value=config.max_occupancy,
                    minimum=1,
                    maximum=10_000,
                    step=1,
                    precision=0,
                    suffix='personas',
                )
                self._parking_spaces = NumberField(
                    'Plazas totales del parking',
                    value=config.parking_spaces,
                    minimum=1,
                    maximum=5_000,
                    step=1,
                    precision=0,
                    suffix='plazas',
                )
        with Panel('Zonas restringidas'):
            Text(
                'El movimiento en una zona restringida genera una alerta y activa los avisos.',
                tag='p',
                classes=f'{Theme.SMALL} {Theme.MUTED}',
            )
            self._zone_switches: dict[str, ui.switch] = {}
            for zone in config.zones:
                row = DefinitionRow(zone.name)
                with row.trailing:
                    self._zone_switches[zone.id] = ui.switch('Restringida', value=zone.restricted).mark(
                        f'zone-{zone.id}'
                    )
                    self._zone_switches[zone.id].on_value_change(self._mark_dirty)
            if not config.zones:
                Text('No hay zonas definidas en configuracion.json.', tag='p', classes=Theme.MUTED)
        for marker, field in (
            ('config-fan', self._fan_threshold),
            ('config-critical', self._critical),
            ('config-occupancy', self._max_occupancy),
            ('config-parking', self._parking_spaces),
            ('config-age', self._max_age),
        ):
            field.input.mark(marker)
            field.input.on_value_change(self._mark_dirty)
        Button('Guardar configuración', variant=ButtonVariant.PRIMARY, on_click=self._save)

    async def _save(self) -> None:
        numbers = (
            self._fan_threshold.value,
            self._critical.value,
            self._max_occupancy.value,
            self._parking_spaces.value,
            self._max_age.value,
        )
        fan_threshold, critical, max_occupancy, parking_spaces, max_age = numbers
        if fan_threshold is None or critical is None or max_occupancy is None or parking_spaces is None:
            ui.notify('Completa todos los campos antes de guardar.', type='warning')
            return
        if any(
            value is not None and not float(value).is_integer() for value in (max_occupancy, parking_spaces, max_age)
        ):
            ui.notify('El aforo, las plazas y la antigüedad deben ser enteros.', type='warning')
            return
        changes = ConfigurationChanges(
            fan_threshold=fan_threshold,
            critical_temperature=critical,
            max_occupancy=round(max_occupancy),
            parking_spaces=round(parking_spaces),
            max_reading_age_minutes=round(max_age) if max_age else None,
            restricted_zone_ids=frozenset(zone_id for zone_id, switch in self._zone_switches.items() if switch.value),
        )
        revision = self._edit_revision

        def saved() -> None:
            self._dirty = self._edit_revision != revision
            self._config.reload()
            self.shell.refresh_alerts()

        await self.act_async(
            lambda actor: self.services.configuration.update(changes, actor), success='Configuración guardada.',
            then=saved,
        )
