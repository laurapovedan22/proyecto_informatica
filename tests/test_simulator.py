"""Generación de lecturas válidas y conservación de las garantías de escritura del Sprint 1."""

from __future__ import annotations

import json
import random
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from lumina.controllers import FixedClock
from lumina.models import Sensor, SensorStatus, SensorType
from lumina.repositories import DataFormatError, Repositories
from lumina.repositories.json_repositories import JsonSensorRepository
from scripts.simular_sensores import SensorSimulator

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize('motion', [False, True])
def test_simulator_writes_readings_that_follow_the_sensor_schema(
    repositories: Repositories,
    clock: FixedClock,
    data_dir: Path,
    motion: bool,
) -> None:
    schema = json.loads((PROJECT_ROOT / 'schemas' / 'sensores.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    before = json.loads((data_dir / 'sensores.json').read_text(encoding='utf-8'))
    simulator = SensorSimulator(repositories, clock, random.Random(7), motion=motion)
    for _ in range(20):
        readings = simulator.step()
        document = json.loads((data_dir / 'sensores.json').read_text(encoding='utf-8'))
        assert list(validator.iter_errors(document)) == []
        assert document['camaras'] == before['camaras']
        for reading in readings:
            assert reading.updated_at == clock.now()
            assert reading.value is not None
            if reading.type is SensorType.PEOPLE_COUNTER:
                assert 0 <= reading.value <= 150 and reading.value.is_integer()
            elif reading.type is SensorType.VEHICLE_COUNTER:
                assert 0 <= reading.value <= 50 and reading.value.is_integer()
            elif reading.type is SensorType.MOTION:
                assert reading.value in (0, 1)
        original_motion = [item for item in before['sensores'] if item['tipo'] == 'movimiento']
        current_motion = [item for item in document['sensores'] if item['tipo'] == 'movimiento']
        if not motion:
            assert current_motion == original_motion
        else:
            assert all(item['actualizado_en'] == clock.now().isoformat() for item in current_motion)


def test_simulator_supports_entries_and_exits(repositories: Repositories, clock: FixedClock) -> None:
    simulator = SensorSimulator(repositories, clock, random.Random(12))
    values: list[float] = []
    for _ in range(25):
        sensor = next(item for item in simulator.step() if item.type is SensorType.PEOPLE_COUNTER)
        assert sensor.value is not None
        values.append(sensor.value)
    differences = [after - before for before, after in pairwise(values)]
    assert any(value > 0 for value in differences)
    assert any(value < 0 for value in differences)


@pytest.mark.parametrize(('start', 'capacity'), [(-10, 150), (999, 150), (20, 0)])
def test_simulator_bounds_each_counter(
    repositories: Repositories,
    clock: FixedClock,
    start: float,
    capacity: int,
) -> None:
    repositories.config.save(replace(repositories.config.load(), max_occupancy=capacity, parking_spaces=capacity))
    for sensor_id in ('aforo-tienda', 'vehiculos-parking'):
        repositories.sensors.modify(sensor_id, lambda sensor: replace(sensor, value=start))
    readings = SensorSimulator(repositories, clock, random.Random(1)).step()
    for reading in readings:
        if reading.type in (SensorType.PEOPLE_COUNTER, SensorType.VEHICLE_COUNTER):
            assert reading.value is not None and 0 <= reading.value <= capacity


def test_simulator_keeps_missing_failed_and_stale_sensors(repositories: Repositories, clock: FixedClock) -> None:
    repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, value=None))
    repositories.sensors.modify('hum-tienda', lambda sensor: replace(sensor, status=SensorStatus.ERROR))
    repositories.sensors.modify('temp-almacen', lambda sensor: replace(sensor, status=SensorStatus.STALE))
    before = repositories.sensors.list_all()
    SensorSimulator(repositories, clock, random.Random(1)).step()
    assert repositories.sensors.list_all()[:3] == before[:3]


def test_simulator_revalidates_the_sensor_inside_modify(
    repositories: Repositories,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = JsonSensorRepository.modify

    def concurrent_change(
        self: JsonSensorRepository,
        sensor_id: str,
        change: Callable[[Sensor], Sensor],
    ) -> Sensor | None:
        if sensor_id == 'temp-tienda':
            original(self, sensor_id, lambda sensor: replace(sensor, status=SensorStatus.ERROR, name='Sensor cambiado'))
        return original(self, sensor_id, change)

    monkeypatch.setattr(JsonSensorRepository, 'modify', concurrent_change)
    readings = SensorSimulator(repositories, clock, random.Random(1)).step()
    sensor = repositories.sensors.get('temp-tienda')
    assert sensor is not None
    assert (sensor.status, sensor.name, sensor.value) == (SensorStatus.ERROR, 'Sensor cambiado', 23.6)
    assert all(reading.id != sensor.id for reading in readings)


def test_simulator_never_overwrites_an_incomplete_file(
    repositories: Repositories,
    clock: FixedClock,
    data_dir: Path,
) -> None:
    simulator = SensorSimulator(repositories, clock, random.Random(1))
    simulator.step()  # calienta la caché del lector
    path = data_dir / 'sensores.json'
    path.write_text('{"sensores": [', encoding='utf-8')
    with pytest.raises(DataFormatError):
        simulator.step()
    assert path.read_text(encoding='utf-8') == '{"sensores": ['


def test_simulator_cli_runs_a_finite_cycle(data_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / 'scripts' / 'simular_sensores.py'),
            '--datos',
            str(data_dir),
            '--ciclos',
            '1',
            '--semilla',
            '7',
            '--movimiento',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '[1]' in result.stdout and 'temp-tienda=' in result.stdout
