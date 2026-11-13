"""Implementación de los repositorios sobre ficheros JSON (fase 1 del proyecto).

Cada clase sabe traducir entre su entidad y el objeto JSON correspondiente
(``_decode``/``_encode``). Las claves de los ficheros están en español porque son el
contrato de datos compartido con la parte IoT; ver el README para el formato completo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import ClassVar, Generic, TypeVar

from ..models import (
    Actuator,
    ActuatorMode,
    ActuatorType,
    Alert,
    AlertStatus,
    AlertType,
    Camera,
    Metric,
    Reading,
    Role,
    Sensor,
    SensorStatus,
    SensorType,
    SystemConfig,
    User,
    Zone,
)
from .interfaces import (
    ActuatorRepository,
    AlertRepository,
    CameraRepository,
    ConfigRepository,
    DuplicateError,
    Identifiable,
    ReadingRepository,
    SensorRepository,
    UserRepository,
)
from .json_store import JsonFile, JsonObject, Record, timestamp_to_json

ItemT = TypeVar('ItemT')
EntityT = TypeVar('EntityT', bound=Identifiable)


class JsonCollection(ABC, Generic[ItemT]):
    """Lista de elementos guardada bajo la clave ``KEY`` de un fichero JSON."""

    KEY: ClassVar[str]

    def __init__(self, file: JsonFile) -> None:
        self._file = file

    def _load(self, *, strict: bool = False) -> list[ItemT]:
        """Elementos del fichero; ``strict`` (al ir a escribir) exige la versión actual y válida."""
        records = Record.list_from(self._file.read(strict=strict), self.KEY, self._file.name)
        return [self._decode(record) for record in records]

    def _store(self, items: Iterable[ItemT]) -> None:
        document = dict(self._file.read(strict=True))  # conserva el resto de claves del fichero
        document[self.KEY] = [self._encode(item) for item in items]
        self._file.write(document)

    @abstractmethod
    def _decode(self, record: Record) -> ItemT:
        """Convierte un objeto JSON en un elemento del modelo."""

    @abstractmethod
    def _encode(self, item: ItemT) -> JsonObject:
        """Convierte un elemento del modelo en un objeto JSON."""


class JsonEntityCollection(JsonCollection[EntityT]):
    """Operaciones CRUD genéricas para entidades con ``id``."""

    def list_all(self) -> list[EntityT]:
        return self._load()

    def add(self, entity: EntityT, *, check: Callable[[list[EntityT]], object] | None = None) -> None:
        with self._file.lock:
            items = self._load(strict=True)
            self._check_new(entity, items)
            if check is not None:
                check(items)
            self._store([*items, entity])

    def update(self, entity: EntityT) -> None:
        with self._file.lock:
            items = self._load(strict=True)
            positions = [index for index, item in enumerate(items) if item.id == entity.id]
            if not positions:
                raise KeyError(f'No existe ningún elemento con id «{entity.id}» en {self._file.name}')
            items[positions[0]] = entity
            self._store(items)

    def modify(self, entity_id: str, change: Callable[[EntityT], EntityT]) -> EntityT | None:
        with self._file.lock:  # leer, cambiar y guardar sin que otra escritura de Lumina se cuele
            items = self._load(strict=True)
            position = next((index for index, item in enumerate(items) if item.id == entity_id), None)
            if position is None:
                return None
            current = items[position]
            updated = change(current)
            if updated is not current:
                items[position] = updated
                self._store(items)
            return updated

    def delete(self, entity_id: str) -> None:
        with self._file.lock:
            items = self._load(strict=True)
            remaining = [item for item in items if item.id != entity_id]
            if len(remaining) != len(items):
                self._store(remaining)

    def _check_new(self, entity: EntityT, items: list[EntityT]) -> None:
        """Lanza :class:`DuplicateError` si ``entity`` choca con un elemento existente."""
        if any(item.id == entity.id for item in items):
            raise DuplicateError(f'Ya existe un elemento con id «{entity.id}» en {self._file.name}')


class JsonUserRepository(JsonEntityCollection[User], UserRepository):
    """``usuarios.json`` › ``usuarios``."""

    KEY = 'usuarios'

    def _check_new(self, entity: User, items: list[User]) -> None:
        super()._check_new(entity, items)
        email = entity.email.casefold()
        if any(item.email.casefold() == email for item in items):
            raise DuplicateError(f'Ya existe una cuenta con el correo «{entity.email}» en {self._file.name}')

    def _decode(self, record: Record) -> User:
        return User(
            id=record.text('id'),
            name=record.text('nombre'),
            email=record.text('email'),
            password_hash=record.text('password_hash'),
            role=record.optional_choice('rol', Role),
            active=record.flag('activo', default=True),
            connected=record.flag('conectado', default=False),
            created_at=record.optional_timestamp('creado_en'),
            last_login_at=record.optional_timestamp('ultimo_acceso'),
            failed_attempts=record.optional_integer('intentos_fallidos') or 0,
            locked=record.flag('bloqueado', default=False),
        )

    def _encode(self, item: User) -> JsonObject:
        return {
            'id': item.id,
            'nombre': item.name,
            'email': item.email,
            'password_hash': item.password_hash,
            'rol': item.role.value if item.role is not None else None,
            'activo': item.active,
            'conectado': item.connected,
            'creado_en': timestamp_to_json(item.created_at),
            'ultimo_acceso': timestamp_to_json(item.last_login_at),
            'intentos_fallidos': item.failed_attempts,
            'bloqueado': item.locked,
        }


class JsonSensorRepository(JsonEntityCollection[Sensor], SensorRepository):
    """``sensores.json`` › ``sensores``."""

    KEY = 'sensores'

    def _decode(self, record: Record) -> Sensor:
        return Sensor(
            id=record.text('id'),
            name=record.text('nombre'),
            type=record.choice('tipo', SensorType),
            zone_id=record.text('zona'),
            value=record.measurement('valor'),
            status=record.optional_choice('estado', SensorStatus) or SensorStatus.ACTIVE,
            updated_at=record.optional_timestamp('actualizado_en'),
        )

    def _encode(self, item: Sensor) -> JsonObject:
        return {
            'id': item.id,
            'nombre': item.name,
            'tipo': item.type.value,
            'zona': item.zone_id,
            'valor': item.value,
            'estado': item.status.value,
            'actualizado_en': timestamp_to_json(item.updated_at),
        }


class JsonCameraRepository(JsonEntityCollection[Camera], CameraRepository):
    """``sensores.json`` › ``camaras``."""

    KEY = 'camaras'

    def _decode(self, record: Record) -> Camera:
        return Camera(
            id=record.text('id'),
            name=record.text('nombre'),
            zone_id=record.text('zona'),
            stream_url=record.optional_text('url'),
            status=record.optional_choice('estado', SensorStatus) or SensorStatus.ACTIVE,
        )

    def _encode(self, item: Camera) -> JsonObject:
        return {
            'id': item.id,
            'nombre': item.name,
            'zona': item.zone_id,
            'url': item.stream_url,
            'estado': item.status.value,
        }


class JsonActuatorRepository(JsonEntityCollection[Actuator], ActuatorRepository):
    """``actuadores.json`` › ``actuadores``."""

    KEY = 'actuadores'

    def _decode(self, record: Record) -> Actuator:
        return Actuator(
            id=record.text('id'),
            name=record.text('nombre'),
            type=record.choice('tipo', ActuatorType),
            zone_id=record.text('zona'),
            is_on=record.flag('encendido', default=False),
            mode=record.optional_choice('modo', ActuatorMode) or ActuatorMode.MANUAL,
            updated_at=record.optional_timestamp('actualizado_en'),
        )

    def _encode(self, item: Actuator) -> JsonObject:
        return {
            'id': item.id,
            'nombre': item.name,
            'tipo': item.type.value,
            'zona': item.zone_id,
            'encendido': item.is_on,
            'modo': item.mode.value,
            'actualizado_en': timestamp_to_json(item.updated_at),
        }


class JsonAlertRepository(JsonEntityCollection[Alert], AlertRepository):
    """``alertas.json`` › ``alertas``."""

    KEY = 'alertas'

    def _decode(self, record: Record) -> Alert:
        return Alert(
            id=record.text('id'),
            type=record.choice('tipo', AlertType),
            zone_id=record.text('zona'),
            created_at=record.timestamp('fecha_hora'),
            status=record.optional_choice('estado', AlertStatus) or AlertStatus.PENDING,
            description=record.optional_text('descripcion') or '',
            sensor_id=record.optional_text('sensor'),
            handled_by=record.optional_text('atendida_por'),
            updated_at=record.optional_timestamp('actualizada_en'),
        )

    def _encode(self, item: Alert) -> JsonObject:
        return {
            'id': item.id,
            'tipo': item.type.value,
            'zona': item.zone_id,
            'fecha_hora': timestamp_to_json(item.created_at),
            'estado': item.status.value,
            'descripcion': item.description,
            'sensor': item.sensor_id,
            'atendida_por': item.handled_by,
            'actualizada_en': timestamp_to_json(item.updated_at),
        }


class JsonReadingRepository(JsonCollection[Reading], ReadingRepository):
    """``historicos.json`` › ``lecturas``."""

    KEY = 'lecturas'

    def list_all(self) -> list[Reading]:
        return self._load()

    def add(self, reading: Reading) -> None:
        with self._file.lock:
            self._store([*self._load(strict=True), reading])

    def _decode(self, record: Record) -> Reading:
        return Reading(
            metric=record.choice('variable', Metric),
            timestamp=record.timestamp('fecha_hora'),
            value=record.number('valor'),
            sensor_status=record.optional_choice('estado', SensorStatus) or SensorStatus.ACTIVE,
        )

    def _encode(self, item: Reading) -> JsonObject:
        return {
            'variable': item.metric.value,
            'fecha_hora': timestamp_to_json(item.timestamp),
            'valor': item.value,
            'estado': item.sensor_status.value,
        }


class JsonConfigRepository(ConfigRepository):
    """``configuracion.json``. Si falta algún campo se usa el valor por defecto."""

    def __init__(self, file: JsonFile) -> None:
        self._file = file

    def load(self) -> SystemConfig:
        defaults = SystemConfig()
        record = Record(self._file.read(), self._file.name)
        zones = tuple(
            Zone(id=zone.text('id'), name=zone.text('nombre'), restricted=zone.flag('restringida', default=False))
            for zone in record.records('zonas')
        )
        max_occupancy = record.optional_integer('aforo_maximo')
        parking_spaces = record.optional_integer('plazas_parking')
        fan_threshold = record.optional_number('umbral_temperatura')
        critical = record.optional_number('temperatura_critica')
        return SystemConfig(
            facility_name=record.optional_text('establecimiento') or defaults.facility_name,
            max_occupancy=defaults.max_occupancy if max_occupancy is None else max_occupancy,
            parking_spaces=defaults.parking_spaces if parking_spaces is None else parking_spaces,
            fan_threshold=defaults.fan_threshold if fan_threshold is None else fan_threshold,
            critical_temperature=defaults.critical_temperature if critical is None else critical,
            max_reading_age_minutes=record.optional_integer('antiguedad_maxima_lectura_min'),
            main_zone_id=record.optional_text('zona_principal') or defaults.main_zone_id,
            zones=zones,
        )

    def save(self, config: SystemConfig) -> None:
        with self._file.lock:
            document = dict(self._file.read(strict=True))
            document.update({
                'establecimiento': config.facility_name,
                'aforo_maximo': config.max_occupancy,
                'plazas_parking': config.parking_spaces,
                'umbral_temperatura': config.fan_threshold,
                'temperatura_critica': config.critical_temperature,
                'antiguedad_maxima_lectura_min': config.max_reading_age_minutes,
                'zona_principal': config.main_zone_id,
                'zonas': [
                    {'id': zone.id, 'nombre': zone.name, 'restringida': zone.restricted} for zone in config.zones
                ],
            })
            self._file.write(document)
