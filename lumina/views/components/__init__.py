"""Componentes reutilizables de la interfaz (solo API Python de NiceGUI)."""

from .base import Box, Heading, Picture, StatusText, Text
from .buttons import Button, ButtonVariant, ClickHandler, NavButton
from .camera import CameraGrid, CameraTile
from .data import DataTable, ProgressMeter, TableRow
from .facility import FacilityMetrics, MotionTable, OccupancyPanels, SensorSummary, SensorTable
from .forms import Field, NumberField, SelectField, TextField
from .layout import AlertBanner, DefinitionRow, MetricCard, MetricGrid, Note, PageHeader, Panel, Toolbar, TwoColumns
from .shell import AppShell, AuthShell, Brand

__all__ = [
    'AlertBanner',
    'AppShell',
    'AuthShell',
    'Box',
    'Brand',
    'Button',
    'ButtonVariant',
    'CameraGrid',
    'CameraTile',
    'ClickHandler',
    'DataTable',
    'DefinitionRow',
    'FacilityMetrics',
    'Field',
    'Heading',
    'MetricCard',
    'MetricGrid',
    'MotionTable',
    'NavButton',
    'Note',
    'NumberField',
    'OccupancyPanels',
    'PageHeader',
    'Panel',
    'Picture',
    'ProgressMeter',
    'SelectField',
    'SensorSummary',
    'SensorTable',
    'StatusText',
    'TableRow',
    'Text',
    'TextField',
    'Toolbar',
    'TwoColumns',
]
