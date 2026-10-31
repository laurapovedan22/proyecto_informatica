"""Dashboard de cada perfil (H1.2: tras iniciar sesión, cada rol llega a su panel).

En el Sprint 1 el dashboard presenta la cuenta y las funciones de cada perfil, y al
administrador el estado de las cuentas. Los datos del establecimiento (aforo, temperatura,
sensores…) se incorporan a partir del Sprint 2.
"""

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

    CURRENT_SPRINT: ClassVar[int] = 1
    SUMMARIES: ClassVar[dict[Role, str]] = {
        Role.ADMIN: 'Gestión de usuarios, permisos y configuración del sistema',
        Role.SECURITY: 'Vigilancia del establecimiento, alertas y actuadores',
        Role.MANAGER: 'Indicadores del supermercado y del parking',
    }
    FEATURES: ClassVar[tuple[RoleFeature, ...]] = (
        RoleFeature('Gestionar cuentas, perfiles y solicitudes', Permission.MANAGE_USERS, 1, Route.USERS),
        RoleFeature('Consultar y modificar tu perfil', None, 1, Route.PROFILE),
        RoleFeature('Supervisar sensores y cámaras', Permission.SUPERVISE, 2),
        RoleFeature('Consultar aforo, parking, temperatura y humedad', Permission.VIEW_FACILITY, 2),
        RoleFeature('Consultar y atender alertas', Permission.MANAGE_ALERTS, 3),
        RoleFeature('Controlar ventiladores, LED y alarma', Permission.CONTROL_ACTUATORS, 3),
        RoleFeature('Configurar umbrales y zonas restringidas', Permission.CONFIGURE_SYSTEM, 3),
        RoleFeature('Consultar históricos y estadísticas', Permission.VIEW_HISTORY, 4),
        RoleFeature('Consultar usuarios conectados y registros de actividad', Permission.VIEW_ACTIVITY, 4),
    )
    """Funciones de los casos de uso del anteproyecto, con el sprint del backlog que las entrega."""

    def render(self) -> None:
        self._account = self.live(lambda: self.services.users.get(self.user.id), self._refresh_user)
        PageHeader(f'Dashboard · {self.role.short_label}', self.SUMMARIES[self.role])
        if self.user.can(Permission.MANAGE_USERS):
            self._counts: LiveData[UserCounts] = self.live(self.services.users.counts, self._accounts.refresh)
            self._accounts()
        with TwoColumns():
            self._account_panel()
            self._features_panel()

    # --- Administración: estado de las cuentas ------------------------------------------------

    @ui.refreshable_method
    def _accounts(self) -> None:
        counts = self._counts.value
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

    def _refresh_user(self) -> None:
        self.user = self._account.value
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
                        Button('Abrir', variant=ButtonVariant.LINK, href=feature.route)
                    else:
                        StatusText(f'Sprint {feature.sprint}', tone=ToneName.MUTED, classes=Theme.SMALL)
            Text(
                'Las funciones marcadas con un sprint se incorporan en esa entrega del Product Backlog.',
                tag='p',
                classes=Theme.NOTE,
            )
