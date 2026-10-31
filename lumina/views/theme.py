"""Estilo visual de Lumina, expresado solo con clases Tailwind generadas desde Python.

La paleta reproduce la del mockup (``lumina-mockups.html``) con su variante oscura. Cada
color es un :class:`Tone` que produce clases como ``bg-[#f4f5f3] dark:bg-[#2b302c]``.
NiceGUI asocia la variante ``dark:`` al modo oscuro de Quasar, así que no hace falta
escribir CSS ni JavaScript.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from nicegui import app, ui


@dataclass(frozen=True, slots=True)
class Tone:
    """Color con su variante para el modo oscuro."""

    light: str
    dark: str

    @property
    def bg(self) -> str:
        return f'bg-[{self.light}] dark:bg-[{self.dark}]'

    @property
    def text(self) -> str:
        return f'text-[{self.light}] dark:text-[{self.dark}]'

    @property
    def border(self) -> str:
        return f'border-[{self.light}] dark:border-[{self.dark}]'


class Palette:
    """Colores del mockup."""

    PAPER = Tone('#ffffff', '#222522')
    SOFT = Tone('#f4f5f3', '#2b302c')
    TEXT = Tone('#292e29', '#eef0ed')
    MUTED = Tone('#60675f', '#b5bdb3')
    LINE = Tone('#d6dbd4', '#4b534b')
    GREEN = Tone('#466347', '#b0c8a7')
    TINT = Tone('#e8eee5', '#3b4a38')
    WARN = Tone('#fff5df', '#473b24')
    WARN_TEXT = Tone('#735018', '#f0d39b')
    DANGER = Tone('#a8321f', '#ff8a75')


class ToneName(StrEnum):
    """Intención de color de un texto de estado."""

    NORMAL = 'normal'
    MUTED = 'muted'
    POSITIVE = 'positive'
    WARNING = 'warning'
    DANGER = 'danger'


class Theme:
    """Clases reutilizables de cada parte de la interfaz (equivalentes a las ``lm-*`` del mockup)."""

    ASSETS_URL = '/assets'
    ICON_URL = f'{ASSETS_URL}/logo-icono.png'

    # Tipografía (los márgenes van aparte para poder omitirlos) ---------------------------------
    H1 = 'text-2xl font-medium leading-tight'
    H2 = 'text-base font-medium leading-snug'
    H3 = 'text-sm font-medium'
    HEADING_SPACING: ClassVar[dict[int, str]] = {1: 'mb-1.5', 2: 'mb-3.5', 3: 'mb-2'}
    SMALL = 'text-xs'
    MUTED = Palette.MUTED.text
    SUBTITLE = f'{Palette.MUTED.text}'
    STRONG = 'font-medium'

    # Estructura -------------------------------------------------------------------------------
    BODY = f'{Palette.TEXT.text} {Palette.PAPER.bg}'
    SHELL = f'w-full min-h-screen flex flex-col sm:flex-row {Palette.PAPER.bg}'
    SIDEBAR = (
        f'w-full sm:w-[180px] shrink-0 flex flex-col px-3.5 py-3.5 sm:py-[22px] {Palette.SOFT.bg} '
        f'border-b sm:border-b-0 sm:border-r {Palette.LINE.border}'
    )
    BRAND = 'flex items-center gap-[9px] text-[22px] tracking-[2px] leading-none mb-1.5 sm:mb-6'
    BRAND_LARGE = 'flex items-center justify-center gap-[9px] text-[26px] tracking-[2px] leading-none mb-7'
    BRAND_ICON = 'w-[37px] h-[32px] object-contain bg-white rounded-sm'
    USER_BOX = 'mb-2.5 sm:mb-4 leading-snug'
    USER_NAME = 'text-[13px] font-medium'
    ROLE = f'text-xs {Palette.MUTED.text}'
    NAV = 'flex flex-row flex-wrap gap-1 sm:flex-col sm:flex-nowrap'
    CONTENT = 'flex-1 min-w-0 max-w-full px-3.5 py-5 sm:p-[22px] lg:p-7'
    PAGE_HEADER = 'mb-6'

    # Bloques ----------------------------------------------------------------------------------
    PANEL = f'w-full border {Palette.LINE.border} rounded p-[18px]'
    PANEL_SPACING = 'mb-[18px]'
    TWO_COLUMNS = 'grid grid-cols-1 md:grid-cols-2 md:gap-x-[18px] w-full'
    METRIC_GRID = 'grid grid-cols-2 gap-3 mb-[22px] w-full'
    METRIC_COLUMNS: ClassVar[dict[int, str]] = {3: 'md:grid-cols-3', 4: 'md:grid-cols-4'}
    METRIC_CARD = f'border {Palette.LINE.border} rounded px-3 py-3.5 min-w-0'
    METRIC_VALUE = 'block text-2xl leading-tight mt-[5px] mb-px whitespace-nowrap tabular-nums'
    ALERT_BANNER = (
        f'w-full flex flex-wrap items-center justify-between gap-3 rounded px-3.5 py-3 mb-[22px] '
        f'{Palette.WARN.bg} {Palette.WARN_TEXT.text}'
    )
    TOOLBAR = 'w-full flex flex-wrap items-center justify-between gap-3 mb-[18px]'
    DEFINITION_ROW = f'flex items-center justify-between gap-3 py-2.5 border-b last:border-b-0 {Palette.LINE.border}'
    BUTTON_ROW = 'flex flex-wrap items-center gap-2'
    NOTE = f'mt-3 text-xs {Palette.MUTED.text}'

    # Tablas -----------------------------------------------------------------------------------
    TABLE_WRAPPER = 'w-full overflow-x-auto'
    TABLE = 'w-full border-collapse text-[13px] text-left'
    TH = f'px-2 py-2.5 font-medium align-middle border-b {Palette.LINE.border} {Palette.SOFT.bg}'
    TD = f'px-2 py-2.5 align-middle border-b {Palette.LINE.border} break-words'

    # Formularios y diálogos -------------------------------------------------------------------
    DIALOG = f'w-full max-w-[420px] rounded p-[18px] shadow-lg {Palette.PAPER.bg} {Palette.TEXT.text}'
    CODE = f'border {Palette.LINE.border} {Palette.SOFT.bg} select-all'
    FORM = 'grid gap-4 w-full max-w-[440px]'
    FIELD = 'grid gap-[5px] w-full'
    AUTH_PAGE = f'w-full min-h-screen flex justify-center px-6 pt-10 pb-[54px] {Palette.PAPER.bg}'
    AUTH_INNER = 'w-full max-w-[350px]'
    AUTH_FORM = 'grid gap-4 w-full mt-[26px]'
    AUTH_FOOTER = 'mt-5 flex items-center justify-center gap-1'

    # Botones ----------------------------------------------------------------------------------
    _BUTTON = 'rounded border px-3 py-[7px] min-h-0 leading-normal font-normal text-sm'
    BUTTON_DEFAULT = f'{_BUTTON} {Palette.PAPER.bg} {Palette.LINE.border} {Palette.TEXT.text}'
    BUTTON_PRIMARY = f'{_BUTTON} {Palette.TINT.bg} {Palette.GREEN.border} {Palette.GREEN.text}'
    BUTTON_DANGER = f'{_BUTTON} {Palette.PAPER.bg} {Palette.LINE.border} {Palette.DANGER.text}'
    BUTTON_LINK = f'p-1 min-h-0 border-0 bg-transparent underline font-normal text-sm {Palette.GREEN.text}'
    # Normal y activo son excluyentes: si se combinaran, los colores competirían entre sí.
    _NAV_BUTTON = 'sm:w-full rounded border px-2.5 py-[9px] min-h-0 leading-normal font-normal text-sm'
    NAV_BUTTON = f'{_NAV_BUTTON} border-transparent bg-transparent {Palette.TEXT.text}'
    NAV_BUTTON_ACTIVE = f'{_NAV_BUTTON} {Palette.TINT.bg} {Palette.GREEN.text} {Palette.LINE.border}'
    LOGOUT = 'mt-2.5 sm:mt-7 self-start sm:self-stretch'

    _TONES: ClassVar[dict[ToneName, str]] = {
        ToneName.NORMAL: '',
        ToneName.MUTED: Palette.MUTED.text,
        ToneName.POSITIVE: Palette.GREEN.text,
        ToneName.WARNING: Palette.WARN_TEXT.text,
        ToneName.DANGER: Palette.DANGER.text,
    }

    @classmethod
    def tone(cls, name: ToneName) -> str:
        return cls._TONES[name]

    @classmethod
    def metric_grid(cls, columns: int) -> str:
        return f'{cls.METRIC_GRID} {cls.METRIC_COLUMNS.get(columns, cls.METRIC_COLUMNS[4])}'

    @staticmethod
    def install() -> None:
        """Colores de Quasar para toda la aplicación (se llama una vez al arrancar)."""
        app.colors(
            primary=Palette.GREEN.light,
            secondary=Palette.MUTED.light,
            accent=Palette.GREEN.light,
            dark=Palette.SOFT.dark,
            dark_page=Palette.PAPER.dark,
            positive=Palette.GREEN.light,
            warning='#c98a1b',
            negative=Palette.DANGER.light,
        )

    @classmethod
    def apply_to_page(cls) -> None:
        """Ajustes comunes a cada página: colores base y sin márgenes por defecto de NiceGUI."""
        ui.query('body').classes(cls.BODY)
        ui.query('.nicegui-content').classes('p-0 gap-0 items-stretch')
