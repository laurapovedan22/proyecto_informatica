"""Bloques de maquetación del mockup: cabecera, cajas, métricas, filas y avisos."""

from __future__ import annotations

from ..theme import Theme, ToneName
from .base import Box, Heading, StatusText, Text
from .buttons import Button, ClickHandler


class PageHeader(Box):
    """Título de la pantalla con su subtítulo (``lm-head``)."""

    def __init__(self, title: str, subtitle: str = '') -> None:
        super().__init__(Theme.PAGE_HEADER, tag='header')
        with self:
            Heading(title, level=1)
            self.subtitle = Text(subtitle, tag='p', classes=Theme.SUBTITLE)


class Panel(Box):
    """Caja con borde y título opcional (``lm-box``)."""

    def __init__(self, title: str | None = None, *, spaced: bool = True, classes: str = '') -> None:
        spacing = Theme.PANEL_SPACING if spaced else ''
        super().__init__(f'{Theme.PANEL} {spacing} {classes}'.strip(), tag='section')
        if title:
            with self:
                Heading(title, level=2)


class Toolbar(Box):
    """Fila con elementos a ambos extremos (``lm-toolbar``)."""

    def __init__(self, *, classes: str = '') -> None:
        super().__init__(f'{Theme.TOOLBAR} {classes}'.strip())


class TwoColumns(Box):
    """Dos columnas que se apilan en pantallas estrechas (``lm-two``)."""

    def __init__(self) -> None:
        super().__init__(Theme.TWO_COLUMNS)


class MetricGrid(Box):
    """Rejilla de tarjetas de métricas (dos columnas en móvil)."""

    def __init__(self, columns: int = 4) -> None:
        super().__init__(Theme.metric_grid(columns))


class MetricCard(Box):
    """Tarjeta con nombre, valor destacado y una línea explicativa (``lm-metric``)."""

    def __init__(self, name: str, value: str, caption: str, *, caption_tone: ToneName = ToneName.MUTED) -> None:
        super().__init__(Theme.METRIC_CARD)
        with self:
            Text(name, classes=f'{Theme.SMALL} {Theme.MUTED}')
            self.value = Text(value, tag='strong', classes=f'{Theme.METRIC_VALUE} font-normal')
            self.caption = StatusText(caption, tone=caption_tone, classes=Theme.SMALL)


class DefinitionRow(Box):
    """Fila «etiqueta ··· valor» separada por una línea (``lm-definition``).

    El lado derecho puede ser un texto (``value``) o cualquier contenido añadido dentro
    de ``row.trailing``.
    """

    def __init__(self, label: str = '', value: str | None = None, *, tone: ToneName = ToneName.POSITIVE) -> None:
        super().__init__(Theme.DEFINITION_ROW)
        with self:
            self.leading = Box('min-w-0')
            if label:
                with self.leading:
                    Text(label)
            self.trailing = Box(f'{Theme.BUTTON_ROW} justify-end text-right')
            if value is not None:
                with self.trailing:
                    StatusText(value, tone=tone)


class AlertBanner(Box):
    """Franja de aviso con una acción opcional (``lm-alert``)."""

    def __init__(self, message: str, *, emphasis: str = '', action: str | None = None,
                 on_action: ClickHandler | None = None) -> None:
        super().__init__(Theme.ALERT_BANNER)
        self.props['role'] = 'status'
        with self:
            with Box(tag='span'):
                if emphasis:
                    Text(emphasis, tag='strong', classes=Theme.STRONG)
                    Text(' · ' if message else '')
                Text(message)
            if action and on_action is not None:
                Button(action, on_click=on_action)


class Note(Text):
    """Texto pequeño y apagado bajo un bloque (``lm-below``)."""

    def __init__(self, text: str) -> None:
        super().__init__(text, tag='p', classes=Theme.NOTE)
