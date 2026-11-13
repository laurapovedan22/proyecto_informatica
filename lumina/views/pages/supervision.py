"""Supervisión de cámaras, zonas y lecturas de sensores (H2.1 y H2.4)."""

from __future__ import annotations

from nicegui import ui

from ...models import Permission
from ..components import Box, PageHeader, Text
from ..components.camera import CameraGrid
from ..components.facility import MotionTable, SensorTable
from ..formatting import Formatter
from ..routes import Route
from ..theme import Theme
from .base import ProtectedPage


class SupervisionPage(ProtectedPage):
    """Consulta reservada a seguridad y administración; revalida el permiso en cada refresco.

    Las cámaras se construyen una vez y en cada refresco solo cambian sus rótulos, para que el
    vídeo siga reproduciéndose; las tablas de zonas y sensores se vuelven a dibujar.
    """

    route = Route.SUPERVISION
    title = 'Supervisión'
    permission = Permission.SUPERVISE

    def render(self) -> None:
        PageHeader(self.title, 'Cámaras, detecciones por zona y estado de los sensores')
        self._reading = Text(tag='p', classes=Theme.READING_NOTE)
        self._camera_area = Box('w-full')
        self._cameras: CameraGrid | None = None
        self._snapshot = self.live(self.services.supervision.snapshot, self._refresh)
        self._content()
        self._show_cameras()
        if self.settings.refresh_seconds > 0:
            ui.timer(1.0, self._tick)  # la hora sobreimpresa en los vídeos avanza cada segundo

    def _refresh(self) -> None:
        self._show_cameras()
        self._content.refresh()

    def _show_cameras(self) -> None:
        snapshot = self._snapshot.value
        if snapshot is None:
            return
        today = self.services.clock.today()
        self._reading.set_text(f'Última lectura: {Formatter.moment(snapshot.last_reading_at, today)}')
        if self._cameras is not None and self._cameras.shows(snapshot.cameras):
            self._cameras.show_feeds(snapshot.cameras, today)
            return
        self._camera_area.clear()  # cámaras nuevas, retiradas o con otra señal: se vuelven a montar
        with self._camera_area:
            self._cameras = CameraGrid(snapshot.cameras, today, self.services.clock.now())

    def _tick(self) -> None:
        if self._cameras is not None:
            self._cameras.show_time(self.services.clock.now())

    @ui.refreshable_method
    def _content(self) -> None:
        snapshot = self._snapshot.value
        if snapshot is None:
            return
        today = self.services.clock.today()
        MotionTable(snapshot.zones, today)
        SensorTable(snapshot.sensors, today)
