"""Lectura y escritura segura de ficheros JSON.

- :class:`JsonFile` relee el fichero solo cuando cambia en disco, de modo que cualquier
  proceso externo (un simulador, el puente con la maqueta IoT…) puede actualizar los datos
  y la aplicación los verá en la siguiente lectura. Las escrituras son atómicas.
- :class:`Record` envuelve un objeto JSON y ofrece getters tipados que fallan con mensajes
  claros (fichero, posición y campo) cuando el formato no es el esperado.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias, TypeVar, cast

JsonValue: TypeAlias = 'str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None'
JsonObject: TypeAlias = dict[str, JsonValue]

EnumT = TypeVar('EnumT', bound=StrEnum)

log = logging.getLogger(__name__)


class DataFormatError(ValueError):
    """El contenido de un fichero JSON no respeta el formato esperado."""


class JsonFile:
    """Documento JSON en disco con caché invalidada por fecha de modificación.

    Si el fichero deja de ser JSON válido (otro proceso lo está escribiendo), durante
    ``grace_seconds`` se sigue usando la última versión válida; si el error persiste, se
    lanza :class:`DataFormatError` para que la interfaz lo muestre.
    """

    def __init__(self, path: Path, *, grace_seconds: float = 3.0) -> None:
        self._path = path
        self._grace_seconds = grace_seconds
        self._lock = threading.RLock()
        self._cache: JsonObject | None = None
        self._version: tuple[int, int] | None = None
        self._invalid_since: float | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def lock(self) -> threading.RLock:
        """Cerrojo reentrante para agrupar lecturas y escrituras (leer-modificar-escribir)."""
        return self._lock

    def read(self, *, strict: bool = False) -> JsonObject:
        """Devuelve el documento (``{}`` si el fichero no existe). No modifiques el resultado.

        Con ``strict`` se exige la versión actual: si el fichero no es JSON válido se lanza
        :class:`DataFormatError` en vez de devolver la última versión válida. Las escrituras lo
        usan para no guardar cambios sobre datos antiguos (y pisar lo que otro proceso escribe).
        """
        with self._lock:
            try:
                stat = self._path.stat()
            except FileNotFoundError:
                return {}
            version = (stat.st_mtime_ns, stat.st_size)
            if self._cache is None or version != self._version:
                try:
                    document = self._load()
                except DataFormatError:
                    now = time.monotonic()
                    if self._invalid_since is None:
                        self._invalid_since = now
                    if strict or self._cache is None or now - self._invalid_since > self._grace_seconds:
                        raise
                    log.warning('No se pudo leer %s; se mantiene la última versión válida', self.name)
                    return self._cache
                self._cache = document
                self._version = version
                self._invalid_since = None
            return self._cache

    def write(self, document: JsonObject) -> None:
        """Guarda el documento de forma atómica (fichero temporal + renombrado)."""
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
            descriptor, temporary = tempfile.mkstemp(dir=self._path.parent, prefix=f'.{self.name}.', suffix='.tmp')
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    handle.write(content)
                os.replace(temporary, self._path)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
            stat = self._path.stat()
            self._cache = document
            self._version = (stat.st_mtime_ns, stat.st_size)

    def _load(self) -> JsonObject:
        try:
            raw: object = json.loads(self._path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise DataFormatError(f'{self.name}: JSON no válido ({error})') from error
        if not isinstance(raw, dict):
            raise DataFormatError(f'{self.name}: la raíz del documento debe ser un objeto JSON')
        return cast(JsonObject, raw)


class Record:
    """Objeto JSON con acceso tipado a sus campos."""

    def __init__(self, data: Mapping[str, JsonValue], source: str) -> None:
        self._data = data
        self._source = source

    @classmethod
    def list_from(cls, document: Mapping[str, JsonValue], key: str, source: str) -> list[Record]:
        """Convierte la lista ``document[key]`` en registros (lista vacía si la clave no existe)."""
        value = document.get(key, [])
        if not isinstance(value, list):
            raise DataFormatError(f'{source}: «{key}» debe ser una lista')
        records: list[Record] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise DataFormatError(f'{source}: {key}[{index}] debe ser un objeto')
            records.append(cls(item, f'{source} › {key}[{index}]'))
        return records

    def has(self, key: str) -> bool:
        return self._data.get(key) is not None

    def text(self, key: str) -> str:
        value = self._require(key)
        if not isinstance(value, str):
            raise self._error(key, 'debe ser un texto')
        return value

    def optional_text(self, key: str) -> str | None:
        return self.text(key) if self.has(key) else None

    def number(self, key: str) -> float:
        value = self._require(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self._error(key, 'debe ser numérico')
        return float(value)

    def optional_number(self, key: str) -> float | None:
        return self.number(key) if self.has(key) else None

    def measurement(self, key: str) -> float | None:
        """Valor de un sensor: número, booleano (``true`` = 1) o ``null``."""
        if not self.has(key):
            return None
        value = self._data[key]
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return self.number(key)

    def integer(self, key: str) -> int:
        value = self._require(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._error(key, 'debe ser un número entero')
        return value

    def optional_integer(self, key: str) -> int | None:
        return self.integer(key) if self.has(key) else None

    def flag(self, key: str, default: bool | None = None) -> bool:
        if not self.has(key) and default is not None:
            return default
        value = self._require(key)
        if not isinstance(value, bool):
            raise self._error(key, 'debe ser true o false')
        return value

    def timestamp(self, key: str) -> datetime:
        """Fecha y hora ISO 8601 (``2026-10-14T14:30:00``) convertida a hora local sin zona."""
        value = self.text(key)
        try:
            moment = datetime.fromisoformat(value)
        except ValueError as error:
            raise self._error(key, 'debe tener formato ISO 8601 (AAAA-MM-DDTHH:MM:SS)') from error
        if moment.tzinfo is not None:
            moment = moment.astimezone().replace(tzinfo=None)
        return moment

    def optional_timestamp(self, key: str) -> datetime | None:
        return self.timestamp(key) if self.has(key) else None

    def choice(self, key: str, enum_type: type[EnumT]) -> EnumT:
        value = self.text(key)
        try:
            return enum_type(value)
        except ValueError as error:
            allowed = ', '.join(member.value for member in enum_type)
            raise self._error(key, f'debe ser uno de: {allowed}') from error

    def optional_choice(self, key: str, enum_type: type[EnumT]) -> EnumT | None:
        return self.choice(key, enum_type) if self.has(key) else None

    def records(self, key: str) -> list[Record]:
        return Record.list_from(self._data, key, self._source)

    def _require(self, key: str) -> JsonValue:
        if key not in self._data or self._data[key] is None:
            raise self._error(key, 'es obligatorio')
        return self._data[key]

    def _error(self, key: str, problem: str) -> DataFormatError:
        return DataFormatError(f'{self._source}: el campo «{key}» {problem}')


def timestamp_to_json(moment: datetime | None) -> str | None:
    """Formato con el que se guardan las fechas en los JSON."""
    return moment.isoformat(timespec='seconds') if moment is not None else None
