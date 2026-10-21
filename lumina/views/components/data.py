"""Tablas de datos.

Se construyen con elementos HTML simples (``table``) desde Python, igual que en el mockup.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..theme import Theme
from .base import Box, Text


class TableRow(Box):
    """Fila de :class:`DataTable`."""

    def __init__(self) -> None:
        super().__init__(tag='tr')

    def text(self, value: str, *, classes: str = '') -> Text:
        """Añade una celda de texto."""
        with self:
            return Text(value, tag='td', classes=f'{Theme.TD} {classes}'.strip())

    def cell(self, *, classes: str = '') -> Box:
        """Añade una celda vacía para meter dentro cualquier elemento (``with row.cell(): …``)."""
        with self:
            return Box(f'{Theme.TD} {classes}'.strip(), tag='td')


class DataTable(Box):
    """Tabla HTML con cabecera y filas añadidas desde Python."""

    def __init__(self, headers: Sequence[str], *, first_column_nowrap: bool = True) -> None:
        super().__init__(Theme.TABLE_WRAPPER)
        self._first_column_nowrap = first_column_nowrap
        with self, Box(Theme.TABLE, tag='table'):
            with Box(tag='thead'), Box(tag='tr'):
                for header in headers:
                    Text(header, tag='th', classes=Theme.TH).props['scope'] = 'col'
            self._body = Box(tag='tbody')

    def row(self) -> TableRow:
        with self._body:
            return TableRow()

    def add_row(self, *values: str) -> TableRow:
        row = self.row()
        for index, value in enumerate(values):
            row.text(value, classes='whitespace-nowrap' if index == 0 and self._first_column_nowrap else '')
        return row
