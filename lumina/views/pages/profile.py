"""Consulta y edición del perfil propio (H1.4 / RF-03)."""

from __future__ import annotations

from nicegui import run, ui

from ...controllers import LuminaError, UserInputValidator
from ...repositories import DataFormatError
from ..components import Box, Button, ButtonVariant, PageHeader, Panel, Text, TextField, TwoColumns
from ..routes import Route
from ..theme import Theme
from .base import ProtectedPage


class ProfilePage(ProtectedPage):
    """Datos personales y cambio de contraseña de cualquier usuario."""

    route = Route.PROFILE
    title = 'Mi perfil'

    def render(self) -> None:
        PageHeader('Mi perfil', 'Consulta y modifica tus datos de acceso')
        with TwoColumns():
            with Panel('Datos personales'), Box(Theme.FORM):
                self._name = TextField(
                    'Nombre', value=self.user.name, autocomplete='name', max_length=UserInputValidator.NAME_MAX_LENGTH,
                    marker='profile-name',
                )
                self._email = TextField(
                    'Correo electrónico', value=self.user.email, autocomplete='email', marker='profile-email'
                )
                Text(f'Perfil: {self.user.role_label}', tag='p', classes=f'{Theme.SMALL} {Theme.MUTED}')
                Button('Guardar cambios', variant=ButtonVariant.PRIMARY, on_click=self._save_profile)
            with Panel('Cambiar contraseña'), Box(Theme.FORM):
                self._current = TextField(
                    'Contraseña actual', password=True, autocomplete='current-password', marker='profile-current'
                )
                self._new = TextField(
                    'Nueva contraseña', password=True, autocomplete='new-password', marker='profile-new'
                )
                self._confirmation = TextField(
                    'Repetir nueva contraseña', password=True, autocomplete='new-password',
                    marker='profile-confirmation',
                )
                Button('Actualizar contraseña', variant=ButtonVariant.PRIMARY, on_click=self._change_password)

    def _save_profile(self) -> None:
        user = self.actor()
        if user is None:
            return
        try:
            self.user = self.services.users.update_profile(user.id, self._name.value, self._email.value)
        except (LuminaError, DataFormatError) as error:
            ui.notify(str(error), type='negative')
            return
        self._name.input.set_value(self.user.name)
        self._email.input.set_value(self.user.email)
        self.shell.show_user(self.user)
        ui.notify('Datos actualizados.', type='positive')

    async def _change_password(self) -> None:
        user = self.actor()
        if user is None:
            return
        try:
            await run.io_bound(
                self.services.users.change_password,
                user.id,
                self._current.value,
                self._new.value,
                self._confirmation.value,
            )
        except (LuminaError, DataFormatError) as error:
            ui.notify(str(error), type='negative')
            return
        for field in (self._current, self._new, self._confirmation):
            field.reset()
        ui.notify('Contraseña actualizada.', type='positive')
