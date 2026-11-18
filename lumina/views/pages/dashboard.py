"""Dashboard por rol: cuentas, establecimiento, alertas y estado de equipos (Sprints 1 a 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from nicegui import ui

from ...models import Permission, Role, UserCounts
from ..components import (
    AlertBanner,
    Box,
    Button,
    ButtonVariant,
    DefinitionRow,
    MetricCard,
    MetricGrid,
    PageHeader,
    Panel,
    StatusText,
    Text,
    TwoColumns,
)
from ..components.facility import FacilityMetrics, OccupancyPanels, SensorSummary
from ..components.incidents import EquipmentPanel, OpenAlertsBanner
from ..formatting import Formatter
from ..routes import Route
from ..theme import Theme, ToneName
from .base import LiveData, ProtectedPage


@dataclass(frozen=True, slots=True)
class RoleFeature:
    """Función de un perfil y sprint del backlog en el que se entrega."""

    label: str
    permission: Permission | None
    """``None``: la tienen todos los perfiles."""
    sprint: int
    route: Route | None = None
    """Pantalla de la función, si ya existe."""


class DashboardPage(ProtectedPage):
    """Resumen inicial. Su contenido depende del rol del usuario."""

    route = Route.DASHBOARD
    title = 'Dashboard'

    CURRENT_SPRINT: ClassVar[int] = 3
    SUMMARIES: ClassVar[dict[Role, str]] = {
        Role.SUPERADMIN: 'Gestión de administradores y cuentas, y supervisión del establecimiento',
        Role.ADMIN: 'Gestión de cuentas y supervisión del establecimiento',
        Role.SECURITY: 'Supervisión de sensores, cámaras y detecciones por zona',
        Role.MANAGER: 'Indicadores del supermercado y del parking',
    }
    FEATURES: ClassVar[tuple[RoleFeature, ...]] = (
        RoleFeature('Gestionar cuentas, perfiles y solicitudes', Permission.MANAGE_USERS, 1, Route.USERS),
        RoleFeature(
            'Gestionar administradores: permisos, cuentas y desbloqueo', Permission.MANAGE_ADMINS, 2, Route.USERS
        ),
        RoleFeature('Consultar y modificar tu perfil', None, 1, Route.PROFILE),
        RoleFeature('Supervisar sensores y cámaras', Permission.SUPERVISE, 2, Route.SUPERVISION),
        RoleFeature('Consultar aforo, parking, temperatura y humedad', Permission.VIEW_FACILITY, 2, Route.DASHBOARD),
        RoleFeature('Consultar y atender alertas', Permission.MANAGE_ALERTS, 3, Route.SUPERVISION),
        RoleFeature('Controlar ventiladores, LED y alarma', Permission.CONTROL_ACTUATORS, 3, Route.SUPERVISION),
        RoleFeature('Configurar umbrales y zonas restringidas', Permission.CONFIGURE_SYSTEM, 3, Route.CONFIGURATION),
        RoleFeature('Consultar históricos y estadísticas', Permission.VIEW_HISTORY, 4),
        RoleFeature('Consultar usuarios conectados y registros de actividad', Permission.VIEW_ACTIVITY, 4),
    )
    """Funciones de los casos de uso del anteproyecto, con el sprint del backlog que las entrega."""

    def render(self) -> None:
        self._account = self.live(lambda: self.services.users.get(self.user.id), self._refresh_user)
        PageHeader(f'Dashboard · {self.role.short_label}', self.SUMMARIES[self.role])
        if self.user.can(Permission.MANAGE_USERS):
            # Las cuentas bloqueadas que se avisan son las que este usuario puede desbloquear.
            self._counts: LiveData[UserCounts] = self.live(
                lambda: self.services.users.counts(self.user), self._accounts.refresh
            )
            self._accounts()
        if self.user.can(Permission.MANAGE_ALERTS):
            self._alerts = self.live(self.services.supervision.open_alerts, self._alerts_panel.refresh)
            self._alerts_panel()
        self._equipment = self.live(self.services.supervision.equipment, self._equipment_panel.refresh)
        self._equipment_panel()
        self._facility = self.live(self.services.facility.status, self._facility_panel.refresh)
        self._facility_panel()
        with TwoColumns():
            self._account_panel()
            self._features_panel()

    # --- Administración: estado de las cuentas ------------------------------------------------

    @ui.refreshable_method
    def _accounts(self) -> None:
        counts = self._counts.value
        if counts is None:
            return
        if counts.pending:
            requests = Formatter.plural(
                counts.pending, 'solicitud de cuenta pendiente', 'solicitudes de cuenta pendientes'
            )
            AlertBanner(
                'El administrador debe asignarles un perfil para que puedan entrar.',
                emphasis=requests,
                action='Revisar solicitudes',
                on_action=lambda: ui.navigate.to(Route.USERS),
            )
        if counts.locked:
            AlertBanner(
                'El administrador debe desbloquearla para que pueda volver a entrar.' if counts.locked == 1
                else 'El administrador debe desbloquearlas para que puedan volver a entrar.',
                emphasis=Formatter.plural(
                    counts.locked, 'cuenta bloqueada por intentos fallidos', 'cuentas bloqueadas por intentos fallidos'
                ),
                action='Revisar cuentas',
                on_action=lambda: ui.navigate.to(Route.USERS),
            )
        with MetricGrid(columns=4):
            MetricCard('Usuarios', str(counts.total), 'Registrados')
            MetricCard('Conectados', str(counts.connected), 'En este momento')
            pending_tone = ToneName.WARNING if counts.pending else ToneName.MUTED
            MetricCard('Solicitudes', str(counts.pending), 'Pendientes de aprobación', caption_tone=pending_tone)
            MetricCard('Desactivadas', str(counts.inactive), 'Cuentas sin acceso')

    # --- Todos los perfiles --------------------------------------------------------------------

    @ui.refreshable_method
    def _facility_panel(self) -> None:
        status = self._facility.value
        if status is None:
            return
        today = self.services.clock.today()
        Text(f'Última lectura: {Formatter.moment(status.last_reading_at, today)}',
             tag='p', classes=Theme.READING_NOTE)
        FacilityMetrics(status, today)
        OccupancyPanels(status)
        if self.user.can(Permission.SUPERVISE):
            SensorSummary(status.sensors)

    def _refresh_user(self) -> None:
        latest = self._account.value
        if latest is None:
            return
        self.user = latest
        self.shell.show_user(self.user)
        self._account_panel.refresh()

    @ui.refreshable_method
    def _account_panel(self) -> None:
        user = self.user
        with Panel('Tu cuenta'):
            DefinitionRow('Nombre', user.name, tone=ToneName.NORMAL)
            DefinitionRow('Correo electrónico', user.email, tone=ToneName.NORMAL)
            DefinitionRow('Perfil', user.role_label, tone=ToneName.NORMAL)
            last_access = Formatter.moment(user.last_login_at, self.services.clock.today())
            DefinitionRow('Último acceso', last_access, tone=ToneName.NORMAL)
            with Box(f'{Theme.BUTTON_ROW} mt-4'):
                Button('Editar mi perfil', href=Route.PROFILE)
                if user.can(Permission.MANAGE_USERS):
                    Button('Gestionar usuarios', variant=ButtonVariant.PRIMARY, href=Route.USERS)

    def _features_panel(self) -> None:
        with Panel('Funciones de tu perfil'):
            for feature in self.FEATURES:
                if feature.permission is not None and not self.user.can(feature.permission):
                    continue
                row = DefinitionRow(feature.label)
                with row.trailing:
                    if feature.sprint <= self.CURRENT_SPRINT and feature.route is not None:
                        if feature.route != self.route:
                            Button('Abrir', variant=ButtonVariant.LINK, href=feature.route)
                        else:
                            StatusText('Disponible en este panel', tone=ToneName.MUTED, classes=Theme.SMALL)
                    else:
                        StatusText(f'Sprint {feature.sprint}', tone=ToneName.MUTED, classes=Theme.SMALL)
            Text(
                'Las funciones marcadas con un sprint se incorporan en esa entrega del Product Backlog.',
                tag='p',
                classes=Theme.NOTE,
            )

    @ui.refreshable_method
    def _alerts_panel(self) -> None:
        alerts = self._alerts.value
        if alerts is not None:  # sin primera lectura válida no se muestra (LiveData reintenta)
            OpenAlertsBanner(alerts, on_review=lambda: ui.navigate.to(Route.SUPERVISION))

    @ui.refreshable_method
    def _equipment_panel(self) -> None:
        equipment = self._equipment.value
        if equipment is not None:
            EquipmentPanel(equipment)
