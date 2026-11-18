"""Acceso a datos (Modelo). Fase 1: ficheros JSON en la carpeta ``data/``."""

from .captures import FileCaptureRepository
from .container import DataFiles, Repositories
from .interfaces import (
    ActuatorRepository,
    AlertRepository,
    CameraRepository,
    CaptureRepository,
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
    'CaptureRepository',
    'ConfigRepository',
    'DataFiles',
    'DataFormatError',
    'DuplicateError',
    'FileCaptureRepository',
    'JsonFile',
    'ReadingRepository',
    'Record',
    'Repositories',
    'Repository',
    'SensorRepository',
    'UserRepository',
]
