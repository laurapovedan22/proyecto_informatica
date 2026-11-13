"""Criterios H2.1–H2.4: cálculos del establecimiento sin interfaz ni funciones de otros sprints."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import TypedDict, Unpack

import pytest

from lumina.controllers import FixedClock, Services
from lumina.models import Sensor, SensorState, SensorStatus, SensorType, Zone
from lumina.repositories import Repositories


class SensorChanges(TypedDict, total=False):
    """Campos editables en las pruebas con el mismo tipo que en Sensor."""

    value: float | None
    status: SensorStatus
    updated_at: datetime | None
    zone_id: str


def change_sensor(repositories: Repositories, sensor_id: str, **fields: Unpack[SensorChanges]) -> None:
    """Edita la versión vigente, como haría el puente de la maqueta IoT."""
    assert repositories.sensors.modify(sensor_id, lambda sensor: replace(sensor, **fields)) is not None


def test_facility_status_matches_the_mockup(services: Services, clock: FixedClock) -> None:
    status = services.facility.status()
    assert (status.climate.temperature, status.climate.humidity) == (23.6, 48)
    assert status.climate.zone.name == 'Zona de tienda'
    assert (status.store.occupied, status.store.capacity, status.store.available) == (86, 150, 64)
    assert (status.parking.occupied, status.parking.capacity, status.parking.available) == (32, 50, 18)
    assert status.store.updated_at == status.parking.updated_at == clock.now()
    assert status.climate.temperature_at == status.climate.humidity_at == status.last_reading_at == clock.now()
    assert all(item.state is SensorState.ACTIVE for item in status.sensors)


@pytest.mark.parametrize(
    ('value', 'stored', 'age', 'limit', 'expected'),
    [
        (None, SensorStatus.ACTIVE, 0, 10, SensorState.NO_DATA),
        (None, SensorStatus.ERROR, 60, 10, SensorState.NO_DATA),
        (23.6, SensorStatus.ERROR, 60, 10, SensorState.ERROR),
        (23.6, SensorStatus.STALE, 0, None, SensorState.STALE),
        (23.6, SensorStatus.ACTIVE, 11, 10, SensorState.STALE),
        (23.6, SensorStatus.ACTIVE, 10, 10, SensorState.ACTIVE),
        (23.6, SensorStatus.ACTIVE, 11, 0, SensorState.ACTIVE),
        (23.6, SensorStatus.ACTIVE, 11, None, SensorState.ACTIVE),
    ],
)
def test_sensor_state_rules(
    repositories: Repositories,
    services: Services,
    clock: FixedClock,
    value: float | None,
    stored: SensorStatus,
    age: int,
    limit: int | None,
    expected: SensorState,
) -> None:
    repositories.config.save(replace(repositories.config.load(), max_reading_age_minutes=limit))
    change_sensor(
        repositories, 'temp-tienda', value=value, status=stored, updated_at=clock.now() - timedelta(minutes=age)
    )
    health = {item.sensor.id: item for item in services.supervision.snapshot().sensors}
    assert health['temp-tienda'].state is expected
    assert health['temp-tienda'].sensor.value == value
    assert health['temp-tienda'].sensor.unit == '°C'
    assert health['temp-tienda'].zone.name == 'Zona de tienda'


@pytest.mark.parametrize('limit', [None, 0, 10])
def test_reading_without_timestamp(repositories: Repositories, services: Services, limit: int | None) -> None:
    repositories.config.save(replace(repositories.config.load(), max_reading_age_minutes=limit))
    change_sensor(repositories, 'temp-tienda', updated_at=None)
    item = next(item for item in services.supervision.snapshot().sensors if item.sensor.id == 'temp-tienda')
    assert item.state is (SensorState.STALE if limit else SensorState.ACTIVE)


def test_old_readings_are_reported_as_stale(
    services: Services,
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    repositories.config.save(replace(repositories.config.load(), max_reading_age_minutes=10))
    clock.advance(timedelta(minutes=30))
    assert all(item.state is SensorState.STALE for item in services.supervision.snapshot().sensors)
    status = services.facility.status()
    assert status.climate.temperature is None and status.climate.humidity is None
    assert status.store.occupied == status.parking.occupied == 0


@pytest.mark.parametrize('literal', ['NaN', 'Infinity', '-Infinity', '1e309', '-1e309'])
def test_nonfinite_json_readings_are_errors_and_never_contribute(
    services: Services, data_dir: Path, literal: str,
) -> None:
    """Incluye el desbordamiento de números JSON válidos, además de NaN e infinitos explícitos."""
    path = data_dir / 'sensores.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    for sensor in document['sensores']:
        sensor['valor'] = 'lectura_no_finita'
    path.write_text(json.dumps(document).replace('"lectura_no_finita"', literal), encoding='utf-8')
    status = services.facility.status()
    assert status.sensors
    assert all(item.state is SensorState.ERROR for item in status.sensors)
    assert all(item.sensor.value is not None and not isfinite(item.sensor.value) for item in status.sensors)
    assert status.store.occupied == status.parking.occupied == 0
    assert status.store.updated_at is status.parking.updated_at is None
    assert status.climate.temperature is status.climate.humidity is None
    assert status.climate.temperature_at is status.climate.humidity_at is None
    snapshot = services.supervision.snapshot()
    assert all(item.state is SensorState.ERROR for item in snapshot.sensors)
    assert all(zone.detected is None for zone in snapshot.zones)
    assert snapshot.cameras[0].motion.state is SensorState.ERROR


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_sensors_do_not_change_valid_aggregates(
    repositories: Repositories, services: Services, value: float,
) -> None:
    for kind in SensorType:
        repositories.sensors.add(Sensor(f'invalido-{kind}', 'Lectura inválida', kind, 'tienda', value))
    status = services.facility.status()
    assert (status.climate.temperature, status.climate.humidity) == (23.6, 48)
    assert (status.store.occupied, status.parking.occupied) == (86, 32)
    assert all(item.state is SensorState.ERROR for item in status.sensors if item.sensor.id.startswith('invalido-'))
    motion = next(zone for zone in services.supervision.snapshot().zones if zone.zone.id == 'tienda')
    assert motion.detected is None and motion.state is SensorState.ERROR


@pytest.mark.parametrize(
    ('value', 'capacity', 'expected'), [(-20, 150, 0), (200, 150, 150), (12, 0, 0), (12.6, 150, 13)]
)
def test_counter_values_are_bounded(
    repositories: Repositories,
    services: Services,
    value: float,
    capacity: int,
    expected: int,
) -> None:
    repositories.config.save(replace(repositories.config.load(), max_occupancy=capacity, parking_spaces=capacity))
    for sensor_id in ('aforo-tienda', 'vehiculos-parking'):
        change_sensor(repositories, sensor_id, value=value)
    status = services.facility.status()
    for result in (status.store, status.parking):
        assert result.occupied == expected
        assert result.available == capacity - expected
        assert 0 <= result.occupied <= capacity
        assert 0 <= result.available <= capacity
        assert 0 <= result.ratio <= 1
    assert repositories.sensors.get('aforo-tienda') is not None
    assert next(item.sensor.value for item in status.sensors if item.sensor.id == 'aforo-tienda') == value


def test_counters_sum_all_operational_sensors(
    repositories: Repositories, services: Services, clock: FixedClock
) -> None:
    repositories.config.save(replace(repositories.config.load(), max_reading_age_minutes=10))
    for kind, original, extra in [
        (SensorType.PEOPLE_COUNTER, 'aforo-tienda', 10),
        (SensorType.VEHICLE_COUNTER, 'vehiculos-parking', 5),
    ]:
        for suffix, value, state, age in [
            ('entrada', extra, SensorStatus.ACTIVE, 0),
            ('salida', -2, SensorStatus.ACTIVE, 0),
            ('fallo', 100, SensorStatus.ERROR, 0),
            ('ausente', None, SensorStatus.ACTIVE, 0),
            ('antiguo', 100, SensorStatus.ACTIVE, 11),
        ]:
            repositories.sensors.add(
                Sensor(
                    f'{original}-{suffix}', suffix, kind, 'tienda', value, state, clock.now() - timedelta(minutes=age)
                )
            )
    status = services.facility.status()
    assert status.store.occupied == 86 + 10 - 2
    assert status.parking.occupied == 32 + 5 - 2


def test_climate_averages_main_zone_and_keeps_its_reading_time(
    repositories: Repositories,
    services: Services,
    clock: FixedClock,
) -> None:
    before = clock.now() - timedelta(minutes=5)
    repositories.sensors.add(
        Sensor('temp-extra', 'Temperatura extra', SensorType.TEMPERATURE, 'tienda', 24.4, updated_at=before)
    )
    climate = services.facility.status().climate
    assert climate.temperature == 24
    assert climate.temperature_at == before
    assert climate.humidity == 48
    assert climate.humidity_at == clock.now()
    change_sensor(repositories, 'temp-tienda', status=SensorStatus.ERROR)
    assert services.facility.status().climate.temperature == 24.4
    change_sensor(repositories, 'temp-extra', value=None)
    assert services.facility.status().climate.temperature is None  # no usa el almacén como si fuera tienda


def test_supervision_has_cameras_motion_zones_and_readings(services: Services) -> None:
    snapshot = services.supervision.snapshot()
    assert [feed.camera.id for feed in snapshot.cameras] == ['cam-almacen', 'cam-parking']
    assert [(feed.zone.name, feed.motion.label) for feed in snapshot.cameras] == [
        ('Almacén', 'Movimiento detectado'),
        ('Parking', 'Sin datos'),
    ]
    zones = {motion.zone.id: motion for motion in snapshot.zones}
    assert zones['almacen'].updated_at == datetime(2026, 10, 14, 14, 25)
    assert zones['salida-emergencia'].label == 'Sin movimiento'
    assert zones['puerta-personal'].label == 'Sin movimiento'
    assert len(snapshot.sensors) == 9


def test_motion_combines_sensors_and_excludes_errors(repositories: Repositories, services: Services) -> None:
    repositories.sensors.add(Sensor('mov-extra', 'Movimiento extra', SensorType.MOTION, 'almacen', 0))
    assert services.supervision.snapshot().cameras[0].motion.detected is True
    change_sensor(repositories, 'mov-almacen', status=SensorStatus.ERROR)
    motion = services.supervision.snapshot().cameras[0].motion
    assert motion.label == 'Sin movimiento'
    assert len(motion.sensors) == 2
    change_sensor(repositories, 'mov-extra', value=None)
    motion = services.supervision.snapshot().cameras[0].motion
    assert motion.detected is None
    assert motion.label == 'Error'


def test_motion_stale_or_missing_never_claims_no_movement(
    repositories: Repositories,
    services: Services,
    clock: FixedClock,
) -> None:
    repositories.config.save(replace(repositories.config.load(), max_reading_age_minutes=1))
    clock.advance(timedelta(minutes=2))
    assert services.supervision.snapshot().cameras[0].motion.label == 'Desactualizado'
    change_sensor(repositories, 'mov-almacen', value=None)
    assert services.supervision.snapshot().cameras[0].motion.label == 'Sin datos'


def test_unconfigured_zones_keep_their_identifier(repositories: Repositories, services: Services) -> None:
    change_sensor(repositories, 'mov-almacen', zone_id='otra-zona')
    snapshot = services.supervision.snapshot()
    assert next(item.zone for item in snapshot.sensors if item.sensor.id == 'mov-almacen') == Zone(
        'otra-zona', 'otra-zona'
    )
    assert next(item for item in snapshot.zones if item.zone.id == 'otra-zona').detected is True


def test_sprint_two_queries_do_not_read_future_modules(services: Services, data_dir: Path) -> None:
    for name in ('actuadores.json', 'alertas.json', 'historicos.json'):
        (data_dir / name).write_text('JSON dañado deliberadamente', encoding='utf-8')
    assert services.facility.status().store.occupied == 86
    assert len(services.supervision.snapshot().cameras) == 2
