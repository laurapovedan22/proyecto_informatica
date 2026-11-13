"""Botones con el aspecto sobrio del mockup."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, TypeAlias

from nicegui import ui
from nicegui.events import ClickEventArguments, Handler

from ..theme import Theme

ClickHandler: TypeAlias = Handler[ClickEventArguments]


class ButtonVariant(StrEnum):
    DEFAULT = 'default'
    PRIMARY = 'primary'
    DANGER = 'danger'
    LINK = 'link'


class Button(ui.button):
    """Botón de Quasar sin mayúsculas, sombras ni color de relleno de Material Design."""

    _STYLES: ClassVar[dict[ButtonVariant, str]] = {
        ButtonVariant.DEFAULT: Theme.BUTTON_DEFAULT,
        ButtonVariant.PRIMARY: Theme.BUTTON_PRIMARY,
        ButtonVariant.DANGER: Theme.BUTTON_DANGER,
        ButtonVariant.LINK: Theme.BUTTON_LINK,
    }

    def __init__(
        self,
        text: str = '',
        *,
        on_click: ClickHandler | None = None,
        variant: ButtonVariant = ButtonVariant.DEFAULT,
        href: str | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(text, on_click=on_click, color=None, icon=icon)
        self.props('flat no-caps')
        self.classes(self._STYLES[variant])
        if href is not None:
            self.props['href'] = href


class NavButton(ui.button):
    """Entrada del menú lateral; es un enlace (``<a href>``) con aspecto de botón."""

    def __init__(self, text: str, *, href: str, active: bool = False) -> None:
        super().__init__(text, color=None)
        self.props('flat no-caps align=left')
        self.props['href'] = href
        self.classes(Theme.NAV_BUTTON_ACTIVE if active else Theme.NAV_BUTTON)
        if active:
            self.props['aria-current'] = 'page'
