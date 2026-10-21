"""Campos de formulario con la etiqueta encima del control, como en el mockup.

Cada campo se envuelve en un ``<label>``: al pulsar el texto se enfoca el control y los
lectores de pantalla asocian ambos sin necesidad de atributos adicionales.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeAlias

from nicegui import ui
from nicegui.events import GenericEventArguments, Handler, ValueChangeEventArguments

from ..theme import Theme
from .base import Box, Text

EnterHandler: TypeAlias = Handler[GenericEventArguments]
ChangeHandler: TypeAlias = Handler[ValueChangeEventArguments[Any]]


class Field(Box):
    """Etiqueta con su control."""

    def __init__(self, label: str, *, classes: str = '') -> None:
        super().__init__(f'{Theme.FIELD} {classes}'.strip(), tag='label')
        with self:
            Text(label)


class TextField(Field):
    """Campo de texto o de contraseña."""

    def __init__(
        self,
        label: str,
        *,
        value: str = '',
        placeholder: str = '',
        password: bool = False,
        autocomplete: str | None = None,
        max_length: int | None = None,
        on_enter: EnterHandler | None = None,
        marker: str | None = None,
    ) -> None:
        super().__init__(label)
        with self:
            self.input = ui.input(value=value, password=password, password_toggle_button=password)
        self.input.props('outlined dense').classes('w-full')
        if marker:
            self.input.mark(marker)
        if placeholder:
            self.input.props['placeholder'] = placeholder
        if autocomplete:
            self.input.props['autocomplete'] = autocomplete
        if max_length:
            self.input.props['maxlength'] = max_length
        if on_enter is not None:
            self.input.on('keydown.enter', on_enter)

    @property
    def value(self) -> str:
        return str(self.input.value or '')

    def reset(self) -> None:
        """Vacía el campo (no confundir con ``Element.clear()``, que elimina los hijos)."""
        self.input.set_value('')


class SelectField(Field):
    """Desplegable con opciones ``{valor: etiqueta}``."""

    def __init__(
        self,
        label: str,
        options: Mapping[str, str],
        *,
        value: str | None = None,
        on_change: ChangeHandler | None = None,
        marker: str | None = None,
    ) -> None:
        super().__init__(label)
        with self:
            self.select = ui.select(dict(options), value=value, on_change=on_change)
        self.select.props('outlined dense options-dense').classes('w-full')
        if marker:
            self.select.mark(marker)

    @property
    def value(self) -> str | None:
        value = self.select.value
        return value if isinstance(value, str) else None
