"""Pantallas de acceso: iniciar sesión y crear cuenta (H1.2 / RF-01)."""

from __future__ import annotations

from functools import partial
from typing import ClassVar

from nicegui import run, ui

from ...controllers import LuminaError, UserInputValidator
from ...repositories import DataFormatError
from ..components import Box, Button, ButtonVariant, Heading, StatusText, Text, TextField
from ..routes import Route
from ..theme import Theme, ToneName
from .base import PublicPage


class LoginPage(PublicPage):
    """Inicio de sesión común a todos los perfiles."""

    route = Route.LOGIN
    title = 'Iniciar sesión'

    DEMO_ACCOUNTS: ClassVar[tuple[tuple[str, str, str], ...]] = (
        ('Administrador', 'ana.lopez@lumina.es', 'admin123'),
        ('Seguridad', 'carlos.ruiz@lumina.es', 'seguridad123'),
        ('Gerente', 'marta.garcia@lumina.es', 'gerente123'),
    )
    """Cuentas de ``data/usuarios.json`` que se ofrecen en modo demostración."""

    def render(self) -> None:
        Heading('Iniciar sesión', classes='text-center')
        Text('Supervisión del supermercado y parking', tag='p', classes=f'{Theme.MUTED} text-center')
        with Box(Theme.AUTH_FORM):
            self._email = TextField(
                'Correo electrónico', placeholder='nombre@ejemplo.com', autocomplete='username',
                on_enter=self._submit, marker='login-email',
            )
            self._password = TextField(
                'Contraseña', placeholder='••••••••', password=True, autocomplete='current-password',
                on_enter=self._submit, marker='login-password',
            )
            self._submit_button = Button('Entrar', variant=ButtonVariant.PRIMARY, on_click=self._submit)
            self._submit_button.classes('w-full')
            self._feedback = StatusText(tone=ToneName.DANGER, tag='p')
            self._feedback.props['role'] = 'alert'
        with Box(Theme.AUTH_FOOTER):
            Text('¿No tienes cuenta?', classes=Theme.SMALL)
            Button('Registrarse', variant=ButtonVariant.LINK, href=Route.REGISTER)
        if self.settings.demo_mode:
            self._demo_accounts()

    async def _submit(self) -> None:
        self._submit_button.disable()
        self._feedback.show('')
        try:
            user = await run.io_bound(self.services.auth.login, self._email.value, self._password.value)
        except (LuminaError, DataFormatError, OSError) as error:
            self._feedback.show(str(error))
            return
        finally:
            self._submit_button.enable()
        if user is None:  # el servidor se está deteniendo
            return
        self._context.session().start(user)
        ui.navigate.to(Route.DASHBOARD)

    def _demo_accounts(self) -> None:
        with Box(f'mt-8 rounded border border-dashed px-3.5 py-3 {Theme.MUTED}'):
            Text('Modo demostración · rellenar con:', tag='p', classes=f'{Theme.SMALL} mb-1')
            for role, email, password in self.DEMO_ACCOUNTS:
                Button(f'{role} ({email})', variant=ButtonVariant.LINK, on_click=partial(self._fill, email, password))

    def _fill(self, email: str, password: str) -> None:
        self._email.input.set_value(email)
        self._password.input.set_value(password)
        self._feedback.show('')


class RegisterPage(PublicPage):
    """Solicitud de cuenta: el administrador asignará después el perfil."""

    route = Route.REGISTER
    title = 'Crear cuenta'

    def render(self) -> None:
        Heading('Crear cuenta', classes='text-center')
        Text('Supervisión del supermercado y parking', tag='p', classes=f'{Theme.MUTED} text-center')
        with Box(Theme.AUTH_FORM):
            self._name = TextField(
                'Nombre', autocomplete='name', max_length=UserInputValidator.NAME_MAX_LENGTH, marker='register-name'
            )
            self._email = TextField(
                'Correo electrónico', placeholder='nombre@ejemplo.com', autocomplete='email', marker='register-email'
            )
            self._password = TextField(
                'Contraseña', placeholder='••••••••', password=True, autocomplete='new-password',
                marker='register-password',
            )
            self._confirmation = TextField(
                'Repetir contraseña', password=True, autocomplete='new-password', on_enter=self._submit,
                marker='register-confirmation',
            )
            Text('El administrador asignará tu perfil de acceso.', tag='p', classes=f'{Theme.SMALL} {Theme.MUTED}')
            self._submit_button = Button('Solicitar cuenta', variant=ButtonVariant.PRIMARY, on_click=self._submit)
            self._submit_button.classes('w-full')
            self._feedback = StatusText(tag='p')
            self._feedback.props['role'] = 'status'
        with Box(Theme.AUTH_FOOTER):
            Text('¿Ya tienes cuenta?', classes=Theme.SMALL)
            Button('Iniciar sesión', variant=ButtonVariant.LINK, href=Route.LOGIN)

    async def _submit(self) -> None:
        self._submit_button.disable()
        try:
            await run.io_bound(
                self.services.auth.register,
                self._name.value,
                self._email.value,
                self._password.value,
                self._confirmation.value,
            )
        except (LuminaError, DataFormatError, OSError) as error:
            self._feedback.show(str(error), ToneName.DANGER)
            return
        finally:
            self._submit_button.enable()
        for field in (self._name, self._email, self._password, self._confirmation):
            field.reset()
        self._feedback.show(
            'Solicitud enviada. Podrás entrar cuando el administrador apruebe tu cuenta.', ToneName.POSITIVE
        )
