"""Agrupa todos los repositorios para inyectarlos en los controladores."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .interfaces import (
    ActuatorRepository,
    AlertRepository,
    CameraRepository,
    ConfigRepository,
    ReadingRepository,
    SensorRepository,
    UserRepository,
)
from .json_repositories import (
    JsonActuatorRepository,
    JsonAlertRepository,
    JsonCameraRepository,
    JsonConfigRepository,
    JsonReadingRepository,
    JsonSensorRepository,
    JsonUserRepository,
)
from .json_store import JsonFile


class DataFiles:
    """Nombres de los ficheros JSON de la carpeta de datos (arquitectura del anteproyecto)."""

    USERS = 'usuarios.json'
    SENSORS = 'sensores.json'
    ACTUATORS = 'actuadores.json'
    ALERTS = 'alertas.json'
    HISTORY = 'historicos.json'
    CONFIGURATION = 'configuracion.json'


@dataclass(frozen=True, slots=True)
class Repositories:
    """Punto único de acceso al Modelo."""

    users: UserRepository
    sensors: SensorRepository
    cameras: CameraRepository
    actuators: ActuatorRepository
    alerts: AlertRepository
    readings: ReadingRepository
    config: ConfigRepository

    @classmethod
    def from_json_dir(cls, data_dir: Path) -> Repositories:
        """Crea los repositorios JSON leyendo los ficheros de ``data_dir``."""
        if not data_dir.is_dir():
            raise FileNotFoundError(f'No existe la carpeta de datos: {data_dir}')
        sensors_file = JsonFile(data_dir / DataFiles.SENSORS)  # sensores y cámaras comparten fichero
        return cls(
            users=JsonUserRepository(JsonFile(data_dir / DataFiles.USERS)),
            sensors=JsonSensorRepository(sensors_file),
            cameras=JsonCameraRepository(sensors_file),
            actuators=JsonActuatorRepository(JsonFile(data_dir / DataFiles.ACTUATORS)),
            alerts=JsonAlertRepository(JsonFile(data_dir / DataFiles.ALERTS)),
            readings=JsonReadingRepository(JsonFile(data_dir / DataFiles.HISTORY)),
            config=JsonConfigRepository(JsonFile(data_dir / DataFiles.CONFIGURATION)),
        )
