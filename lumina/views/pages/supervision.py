"""Supervisión de cámaras, zonas y lecturas de sensores (H2.1 y H2.4), con el análisis de imagen de YOLO."""

from __future__ import annotations

from nicegui import ui

from ...models import AlertStatus, Permission, VisionState
from ..components import Box, PageHeader, Text
from ..components.camera import CameraGrid
from ..components.facility import MotionTable, SensorTable
from ..components.incidents import AlertList, EquipmentPanel
from ..formatting import Formatter
from ..routes import Route
from ..theme import Theme
from .base import ProtectedPage


class SupervisionPage(ProtectedPage):
    """Consulta reservada a seguridad y administración; revalida el permiso en cada refresco.

    Las cámaras se construyen una vez y en cada refresco solo cambian sus rótulos, para que el
    vídeo siga reproduciéndose; alertas, equipos, zonas y sensores se vuelven a dibujar.
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
            self._cameras.show_vision(self._vision_note())
            return
        self._camera_area.clear()  # cámaras nuevas, retiradas o con otra señal: se vuelven a montar
        with self._camera_area:
            self._cameras = CameraGrid(snapshot.cameras, today, self.services.clock.now())
        self._cameras.show_vision(self._vision_note())

    def _vision_note(self) -> str:
        """Qué hace el análisis de imagen o, si no está funcionando, por qué."""
        if not self.settings.vision or self.settings.refresh_seconds <= 0:
            return 'Análisis de imagen con YOLO desactivado.'
        status = self.services.vision.status
        if status.state is VisionState.UNAVAILABLE:
            return f'Análisis de imagen no disponible: {status.detail}.'
        if status.state is VisionState.STARTING:
            return 'Análisis de imagen con YOLO: preparando el modelo…'
        return (
            f'Análisis de imagen con {status.detail} cada {Formatter.number(self.settings.refresh_seconds)} s: '
            'una persona en una zona restringida enciende el LED y la alarma y abre una alerta con su imagen.'
        )

    def _tick(self) -> None:
        if self._cameras is not None:
            self._cameras.show_time(self.services.clock.now())
            self._cameras.show_vision(self._vision_note())  # p. ej., cuando YOLO termina de cargarse

    @ui.refreshable_method
    def _content(self) -> None:
        snapshot = self._snapshot.value
        if snapshot is None:
            return
        today = self.services.clock.today()
        AlertList(snapshot.alerts, today, self._set_alert if self.user.can(Permission.MANAGE_ALERTS) else None)
        EquipmentPanel(
            snapshot.actuators,
            on_switch=self._set_actuator if self.user.can(Permission.CONTROL_ACTUATORS) else None,
            on_automatic=self._set_automatic if self.user.can(Permission.CONTROL_ACTUATORS) else None,
        )
        MotionTable(snapshot.zones, today)
        SensorTable(snapshot.sensors, today)

    def _set_alert(self, alert_id: str, status: AlertStatus) -> None:
        if self.act(lambda actor: self.services.supervision.update_alert(alert_id, status, actor),
                    success='Estado de la alerta actualizado.'):
            self._snapshot.reload()
            self.shell.refresh_alerts()

    def _set_actuator(self, actuator_id: str, on: bool) -> None:
        if self.act(lambda actor: self.services.supervision.set_actuator(actuator_id, on, actor),
                    success='Estado del equipo actualizado.'):
            self._snapshot.reload()

    async def _set_automatic(self, actuator_id: str) -> None:
        await self.act_async(
            lambda actor: self.services.supervision.set_automatic(actuator_id, actor),
            success='Ventilador en modo automático.',
            then=self._snapshot.reload,
        )
