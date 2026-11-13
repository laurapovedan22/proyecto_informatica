"""Acceso a datos (Modelo). Fase 1: ficheros JSON en la carpeta ``data/``."""

from .container import DataFiles, Repositories
from .interfaces import (
    ActuatorRepository,
    AlertRepository,
    CameraRepository,
    ConfigRepository,
    DuplicateError,
    ReadingRepository,
    Repository,
    SensorRepository,
    UserRepository,
)
from .json_store import DataFormatError, JsonFile, Record

__all__ = [
    'ActuatorRepository',
    'AlertRepository',
    'CameraRepository',
    'ConfigRepository',
    'DataFiles',
    'DataFormatError',
    'DuplicateError',
    'JsonFile',
    'ReadingRepository',
    'Record',
    'Repositories',
    'Repository',
    'SensorRepository',
    'UserRepository',
]
