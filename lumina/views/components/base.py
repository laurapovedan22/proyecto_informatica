"""Elementos básicos: contenedores, textos con etiqueta HTML semántica e imágenes."""

from __future__ import annotations

from typing import ClassVar

from nicegui.element import Element
from nicegui.elements.mixins.text_element import TextElement

from ..theme import Theme, ToneName


class Box(Element):
    """Contenedor HTML (``div`` por defecto) con clases Tailwind."""

    def __init__(self, classes: str = '', *, tag: str = 'div') -> None:
        super().__init__(tag)
        if classes:
            self.classes(classes)


class Text(TextElement):
    """Texto dentro de cualquier etiqueta (``span``, ``p``, ``strong``, ``td``…)."""

    def __init__(self, text: str = '', *, tag: str = 'span', classes: str = '') -> None:
        super().__init__(tag=tag, text=text)
        if classes:
            self.classes(classes)


class Heading(Text):
    """Título ``h1``-``h3`` con la tipografía del mockup.

    ``spaced=False`` quita el margen inferior (por ejemplo, dentro de una barra de herramientas).
    """

    _STYLES: ClassVar[dict[int, str]] = {1: Theme.H1, 2: Theme.H2, 3: Theme.H3}

    def __init__(self, text: str, level: int = 1, *, spaced: bool = True, classes: str = '') -> None:
        level = level if level in self._STYLES else 3
        spacing = Theme.HEADING_SPACING[level] if spaced else ''
        super().__init__(text, tag=f'h{level}', classes=f'{self._STYLES[level]} {spacing} {classes}'.strip())


class StatusText(Text):
    """Texto de estado coloreado según su intención (correcto, aviso, error…)."""

    def __init__(
        self, text: str = '', *, tone: ToneName = ToneName.NORMAL, tag: str = 'span', classes: str = ''
    ) -> None:
        super().__init__(text, tag=tag, classes=classes)
        self._tone = tone
        self.classes(Theme.tone(tone))

    def show(self, text: str, tone: ToneName | None = None) -> None:
        """Cambia el texto y, opcionalmente, el color."""
        if tone is not None and tone is not self._tone:
            self.classes(remove=Theme.tone(self._tone))
            self.classes(Theme.tone(tone))
            self._tone = tone
        self.set_text(text)


class Picture(Element):
    """Imagen HTML simple (``<img>``)."""

    def __init__(self, source: str, *, alt: str = '', classes: str = '') -> None:
        super().__init__('img')
        self.props['src'] = source
        self.props['alt'] = alt
        if classes:
            self.classes(classes)
