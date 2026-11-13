"""Esquemas JSON (H1.1): los datos cumplen el contrato documentado en ``schemas/``.

Son la referencia para quien escriba los JSON desde fuera (simulador, maqueta IoT) en los
siguientes sprints: si un cambio de formato no actualiza el esquema, estos tests fallan.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from lumina.controllers import AuthenticationError, Services
from lumina.models import Role, User
from lumina.repositories import Repositories

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
SCHEMAS_DIR = PROJECT_ROOT / 'schemas'
DATA_FILES = sorted(path.name for path in DATA_DIR.glob('*.json'))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load(SCHEMAS_DIR / name.replace('.json', '.schema.json')))


def errors(name: str, document: Any) -> list[str]:
    return sorted(f'{list(error.absolute_path)}: {error.message}' for error in validator(name).iter_errors(document))


def documented_fields(schema: Any, path: str = '') -> Iterator[tuple[str, Any]]:
    """Cada propiedad definida en el esquema, con su ruta."""
    if isinstance(schema, dict):
        for name, definition in schema.get('properties', {}).items():
            yield f'{path}.{name}', definition
        for key, value in schema.items():
            yield from documented_fields(value, f'{path}/{key}')
    elif isinstance(schema, list):
        for item in schema:
            yield from documented_fields(item, path)


def test_every_data_file_has_its_schema() -> None:
    schemas = sorted(path.name.replace('.schema.json', '.json') for path in SCHEMAS_DIR.glob('*.schema.json'))
    assert schemas == DATA_FILES
    assert {'usuarios.json', 'sensores.json', 'actuadores.json', 'alertas.json', 'historicos.json'} <= set(DATA_FILES)


@pytest.mark.parametrize('name', DATA_FILES)
def test_sample_data_follows_its_schema(name: str) -> None:
    Draft202012Validator.check_schema(load(SCHEMAS_DIR / name.replace('.json', '.schema.json')))
    assert errors(name, load(DATA_DIR / name)) == []


@pytest.mark.parametrize('name', DATA_FILES)
def test_every_field_is_documented(name: str) -> None:
    schema = load(SCHEMAS_DIR / name.replace('.json', '.schema.json'))
    assert schema.get('description')
    undocumented = [path for path, field in documented_fields(schema) if not field.get('description')]
    assert undocumented == []


def first(document: Any, key: str) -> dict[str, Any]:
    item = document[key][0]
    assert isinstance(item, dict)
    return item


@pytest.mark.parametrize(
    ('name', 'change'),
    [
        ('usuarios.json', lambda doc: first(doc, 'usuarios').update(rol='jefe')),
        ('usuarios.json', lambda doc: first(doc, 'usuarios').update(password_hash='gerente123')),
        ('usuarios.json', lambda doc: first(doc, 'usuarios').pop('email')),
        ('usuarios.json', lambda doc: first(doc, 'usuarios').update(intentos_fallidos=-1)),
        ('usuarios.json', lambda doc: first(doc, 'usuarios').update(bloqueado='sí')),
        ('sensores.json', lambda doc: first(doc, 'sensores').update(tipo='presion')),
        ('sensores.json', lambda doc: first(doc, 'sensores').update(valor='alto')),
        ('actuadores.json', lambda doc: first(doc, 'actuadores').update(encendido='sí')),
        ('alertas.json', lambda doc: first(doc, 'alertas').update(estado='cerrada')),
        ('historicos.json', lambda doc: first(doc, 'lecturas').update(fecha_hora='14/10/2026 9:00')),
        ('configuracion.json', lambda doc: doc.update(aforo_maximo=-1)),
        ('configuracion.json', lambda doc: doc.update(zona_pricipal='tienda')),  # errata: campo desconocido
    ],
)
def test_schemas_reject_invalid_data(name: str, change: Callable[[Any], object]) -> None:
    document = load(DATA_DIR / name)
    change(document)
    assert errors(name, document) != []


def test_identifiers_and_zones_are_consistent() -> None:
    users = load(DATA_DIR / 'usuarios.json')['usuarios']
    assert len({user['id'] for user in users}) == len(users)
    assert len({user['email'].casefold() for user in users}) == len(users)
    zones = {zone['id'] for zone in load(DATA_DIR / 'configuracion.json')['zonas']}
    references = [
        *load(DATA_DIR / 'sensores.json')['sensores'],
        *load(DATA_DIR / 'sensores.json')['camaras'],
        *load(DATA_DIR / 'actuadores.json')['actuadores'],
        *load(DATA_DIR / 'alertas.json')['alertas'],
    ]
    assert {item['zona'] for item in references} <= zones


def test_what_the_application_writes_follows_the_schemas(services: Services, admin: User, data_dir: Path) -> None:
    services.auth.register('Lucía Fernández', 'lucia@lumina.es', 'secreta1', 'secreta1')
    services.users.create('Pedro Gil', 'pedro@lumina.es', Role.SECURITY, admin)
    services.users.update_account('usr-marta', 'Marta García Ruiz', 'marta.ruiz@lumina.es', admin)
    services.auth.login('carlos.ruiz@lumina.es', 'seguridad123')
    for _ in range(3):  # la tercera contraseña incorrecta bloquea la cuenta
        with pytest.raises(AuthenticationError):
            services.auth.login('pedro@lumina.es', 'incorrecta')
    assert errors('usuarios.json', load(data_dir / 'usuarios.json')) == []


def test_every_repository_writes_what_its_schema_describes(repositories: Repositories, data_dir: Path) -> None:
    """Contrato de escritura de H1.1: lo que guarda la aplicación vuelve a cumplir los esquemas."""
    for sensor in repositories.sensors.list_all():
        repositories.sensors.update(sensor)
    for camera in repositories.cameras.list_all():
        repositories.cameras.update(camera)
    for actuator in repositories.actuators.list_all():
        repositories.actuators.update(actuator)
    for alert in repositories.alerts.list_all():
        repositories.alerts.update(alert)
    repositories.readings.add(repositories.readings.list_all()[0])
    repositories.config.save(repositories.config.load())
    for name in DATA_FILES:
        assert errors(name, load(data_dir / name)) == [], name
