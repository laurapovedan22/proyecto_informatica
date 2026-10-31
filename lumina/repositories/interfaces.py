"""Contratos de acceso a datos.

Los controladores solo conocen estas clases abstractas. En la fase 1 se implementan con
ficheros JSON (:mod:`lumina.repositories.json_repositories`); en la fase 2 bastará con
escribir otras implementaciones (por ejemplo ``SqlUserRepository``) sin tocar ni los
controladores ni las vistas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Generic, Protocol, TypeVar

from ..models import Actuator, Alert, Camera, Reading, Sensor, SystemConfig, User


class Identifiable(Protocol):
    """Cualquier entidad con un identificador de texto."""

    @property
    def id(self) -> str: ...


class DuplicateError(ValueError):
    """Ya existe un elemento con el mismo ``id`` (o, en los usuarios, con el mismo correo)."""


EntityT = TypeVar('EntityT', bound=Identifiable)


class Repository(ABC, Generic[EntityT]):
    """Colección de entidades identificadas por ``id``."""

    @abstractmethod
    def list_all(self) -> list[EntityT]:
        """Todas las entidades, en el orden en que están guardadas."""

    @abstractmethod
    def add(self, entity: EntityT, *, check: Callable[[list[EntityT]], object] | None = None) -> None:
        """Añade una entidad nueva. Lanza :class:`DuplicateError` si el ``id`` ya existe.

        ``check`` recibe las entidades actuales justo antes de guardar, en la misma transacción, y
        puede lanzar una excepción para que no se añada nada.
        """

    @abstractmethod
    def update(self, entity: EntityT) -> None:
        """Sustituye la entidad con el mismo ``id``. Lanza ``KeyError`` si no existe."""

    @abstractmethod
    def delete(self, entity_id: str) -> None:
        """Elimina la entidad (no hace nada si no existe)."""

    def get(self, entity_id: str) -> EntityT | None:
        return next((entity for entity in self.list_all() if entity.id == entity_id), None)

    def modify(self, entity_id: str, change: Callable[[EntityT], EntityT]) -> EntityT | None:
        """Aplica ``change`` a la versión actual de la entidad y guarda el resultado.

        Devuelve la entidad guardada, o ``None`` si no existe. Si ``change`` devuelve la misma
        entidad no se escribe nada, y si lanza una excepción tampoco. Las implementaciones deben
        hacerlo de forma atómica, para que ninguna otra escritura se cuele entre leer y guardar.
        """
        current = self.get(entity_id)
        if current is None:
            return None
        updated = change(current)
        if updated is not current:
            self.update(updated)
        return updated


class UserRepository(Repository[User], ABC):
    """Usuarios de la plataforma. ``add`` también lanza :class:`DuplicateError` si el correo ya existe."""

    def find_by_email(self, email: str) -> User | None:
        normalized = email.strip().casefold()
        return next((user for user in self.list_all() if user.email.casefold() == normalized), None)


class SensorRepository(Repository[Sensor], ABC):
    """Última lectura de cada sensor."""


class CameraRepository(Repository[Camera], ABC):
    """Cámaras de vigilancia."""


class ActuatorRepository(Repository[Actuator], ABC):
    """Estado de los actuadores (ventiladores, LED, alarma)."""


class AlertRepository(Repository[Alert], ABC):
    """Alertas e incidencias."""


class ReadingRepository(ABC):
    """Histórico de lecturas para estadísticas (se consultará en el Sprint 4)."""

    @abstractmethod
    def list_all(self) -> list[Reading]: ...

    @abstractmethod
    def add(self, reading: Reading) -> None: ...


class ConfigRepository(ABC):
    """Configuración del establecimiento (un único documento)."""

    @abstractmethod
    def load(self) -> SystemConfig: ...

    @abstractmethod
    def save(self, config: SystemConfig) -> None: ...
