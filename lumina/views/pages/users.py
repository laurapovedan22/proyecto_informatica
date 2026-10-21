"""Gestión de cuentas y perfiles (H1.3 / RF-02): listado, alta, edición, desactivación y rol."""

from __future__ import annotations

from functools import partial
from typing import Any, ClassVar

from nicegui import run, ui
from nicegui.events import ValueChangeEventArguments

from ...controllers import LuminaError, UserInputValidator
from ...models import Permission, Role, User
from ...repositories import DataFormatError
from ..components import (
    Box,
    Button,
    ButtonVariant,
    DataTable,
    Heading,
    Note,
    PageHeader,
    Panel,
    SelectField,
    StatusText,
    Text,
    TextField,
    Toolbar,
)
from ..formatting import Formatter
from ..routes import Route
from ..theme import Theme, ToneName
from .base import ProtectedPage


class UsersPage(ProtectedPage):
    """Listado de cuentas, alta, edición, desactivación y asignación de perfiles (solo administración)."""

    route = Route.USERS
    title = 'Usuarios'
    permission = Permission.MANAGE_USERS

    ROLE_OPTIONS: ClassVar[dict[str, str]] = {
        role.value: role.label for role in (Role.MANAGER, Role.SECURITY, Role.ADMIN)
    }

    def render(self) -> None:
        PageHeader('Usuarios', 'Gestionar accesos y perfiles')
        with Toolbar():
            self._summary = Text()
            self._toggle_button = Button('Añadir usuario', variant=ButtonVariant.PRIMARY, on_click=self._toggle_form)
        self._form = self._build_form()
        self._form.set_visibility(False)
        self._dialogs = Box()
        self._users = self.live(self.services.users.list_users, self._table.refresh)
        self._table()
        Note('El administrador asigna el perfil de cada usuario. Las solicitudes de registro aparecen primero, '
             'como «Pendiente de aprobación», hasta que se les asigna un perfil. Una cuenta desactivada no puede '
             'iniciar sesión.')

    # --- Tabla --------------------------------------------------------------------------------

    @ui.refreshable_method
    def _table(self) -> None:
        users = self._users.value
        connected = sum(1 for user in users if user.connected)
        self._summary.set_text(
            f'{Formatter.plural(len(users), "usuario", "usuarios")} · '
            f'{Formatter.plural(connected, "conectado", "conectados")}'
        )
        table = DataTable(['Nombre', 'Perfil', 'Estado', 'Acciones'])
        for user in users:
            self._row(table, user)

    def _row(self, table: DataTable, user: User) -> None:
        is_self = user.id == self.user.id
        row = table.row()
        with row.cell(classes='min-w-[160px]'):
            Text(user.name, classes='block')
            Text(user.email, classes=f'{Theme.SMALL} {Theme.MUTED}')
        with row.cell(classes='min-w-[200px]'):
            select = ui.select(
                self.ROLE_OPTIONS,
                value=user.role.value if user.role is not None else None,
                on_change=partial(self._change_role, user.id),
            ).props('outlined dense options-dense').classes('w-full').mark(f'role-{user.id}')
            select.props['aria-label'] = f'Perfil de {user.name}'
            if user.role is None:
                select.props['label'] = 'Asignar perfil'
            if is_self:
                select.disable()
        with row.cell():
            label, tone = self._state(user)
            StatusText(label, tone=tone)
        with row.cell(classes='whitespace-nowrap'):
            if is_self:
                Text('Tu cuenta', classes=f'{Theme.SMALL} {Theme.MUTED}')
            else:
                with Box(Theme.BUTTON_ROW):
                    Button('Editar', on_click=partial(self._edit_account, user)).mark(f'edit-{user.id}')
                    Button(
                        'Desactivar' if user.active else 'Activar',
                        variant=ButtonVariant.DANGER if user.active else ButtonVariant.DEFAULT,
                        on_click=partial(self._set_active, user.id, not user.active),
                    ).mark(f'active-{user.id}')

    @staticmethod
    def _state(user: User) -> tuple[str, ToneName]:
        if user.is_pending:
            return 'Pendiente de aprobación', ToneName.WARNING
        if not user.active:
            return 'Desactivada', ToneName.DANGER
        if user.connected:
            return 'Conectado', ToneName.POSITIVE
        return 'Desconectado', ToneName.MUTED

    # --- Acciones -----------------------------------------------------------------------------

    def _change_role(self, user_id: str, event: ValueChangeEventArguments[Any]) -> None:
        if isinstance(event.value, str):
            role = Role(event.value)
            self.act(lambda actor: self.services.users.change_role(user_id, role, actor), success='Perfil actualizado.')
        self._users.reload()

    def _set_active(self, user_id: str, active: bool) -> None:
        message = 'Cuenta reactivada.' if active else 'Cuenta desactivada.'
        self.act(lambda actor: self.services.users.set_active(user_id, active, actor), success=message)
        self._users.reload()

    async def _edit_account(self, user: User) -> None:
        with self._dialogs, ui.dialog() as dialog, Box(Theme.DIALOG):
            Heading('Editar usuario', level=2)
            with Box(Theme.FORM):
                name = TextField(
                    'Nombre', value=user.name, autocomplete='off', max_length=UserInputValidator.NAME_MAX_LENGTH,
                    marker='edit-name',
                )
                email = TextField('Correo electrónico', value=user.email, autocomplete='off', marker='edit-email')
            Text('El perfil y el estado se cambian desde la tabla.', tag='p', classes=f'{Theme.NOTE} mb-5')
            with Box(f'{Theme.BUTTON_ROW} justify-end'):
                Button('Cancelar', on_click=lambda: dialog.submit(False))
                Button(
                    'Guardar cambios',
                    variant=ButtonVariant.PRIMARY,
                    on_click=lambda: self._save_account(dialog, user.id, name, email),
                ).mark('edit-save')
        await dialog
        dialog.delete()

    def _save_account(self, dialog: ui.dialog, user_id: str, name: TextField, email: TextField) -> None:
        saved = self.act(
            lambda actor: self.services.users.update_account(user_id, name.value, email.value, actor),
            success='Datos del usuario actualizados.',
        )
        if saved:
            dialog.submit(True)
            self._users.reload()

    # --- Alta de usuarios ---------------------------------------------------------------------

    def _build_form(self) -> Panel:
        with Panel('Nuevo usuario', classes='max-w-[440px]') as panel, Box(Theme.FORM):
            self._new_name = TextField(
                'Nombre', max_length=UserInputValidator.NAME_MAX_LENGTH, autocomplete='off', marker='new-name'
            )
            self._new_email = TextField('Correo', autocomplete='off', marker='new-email')
            self._new_role = SelectField('Perfil', self.ROLE_OPTIONS, value=Role.MANAGER.value)
            Button('Guardar usuario', variant=ButtonVariant.PRIMARY, on_click=self._create_user).classes('w-full')
        return panel

    def _toggle_form(self) -> None:
        visible = not self._form.visible
        self._form.set_visibility(visible)
        self._toggle_button.set_text('Cancelar' if visible else 'Añadir usuario')

    async def _create_user(self) -> None:
        actor = self.actor()
        if actor is None:
            return
        role = Role(self._new_role.value or Role.MANAGER.value)
        try:
            credentials = await run.io_bound(
                self.services.users.create, self._new_name.value, self._new_email.value, role, actor
            )
        except (LuminaError, DataFormatError) as error:
            ui.notify(str(error), type='negative')
            return
        if credentials is None or self.actor() is None:  # si acaba de perder el acceso, no ve la contraseña
            return
        self._new_name.reset()
        self._new_email.reset()
        self._toggle_form()
        self._users.reload()
        await self._show_password(credentials.user, credentials.temporary_password)

    async def _show_password(self, user: User, password: str) -> None:
        with self._dialogs, ui.dialog() as dialog, Box(Theme.DIALOG):
            Heading('Usuario creado', level=2)
            Text(f'Comparte esta contraseña temporal con {user.name}. Podrá cambiarla desde «Mi perfil».',
                 tag='p', classes='mb-3')
            Text(password, tag='p', classes=f'font-mono text-lg mb-5 px-3 py-2 rounded {Theme.CODE}')
            with Box(f'{Theme.BUTTON_ROW} justify-end'):
                Button('Copiar', on_click=lambda: ui.clipboard.write(password))
                Button('Entendido', variant=ButtonVariant.PRIMARY, on_click=lambda: dialog.submit(True))
        await dialog
        dialog.delete()
