"""Capa JSON (H1.1): lectura tipada, detección de cambios externos y escritura atómica."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from lumina.models import Metric, SensorStatus, SensorType
from lumina.repositories import DataFormatError, JsonFile, Record, Repositories


def test_sample_data_loads(repositories: Repositories) -> None:
    assert len(repositories.users.list_all()) == 3
    assert {sensor.type for sensor in repositories.sensors.list_all()} >= {
        SensorType.TEMPERATURE, SensorType.HUMIDITY, SensorType.MOTION, SensorType.PEOPLE_COUNTER,
    }
    assert len(repositories.cameras.list_all()) == 2
    assert len(repositories.actuators.list_all()) == 3
    assert len(repositories.readings.list_all()) == 48
    assert repositories.config.load().max_occupancy == 150


def test_motion_sensor_accepts_booleans(repositories: Repositories) -> None:
    motion = repositories.sensors.get('mov-almacen')
    assert motion is not None
    assert motion.value == 1.0  # «true» en el JSON = movimiento detectado


def test_external_changes_are_detected(data_dir: Path, repositories: Repositories) -> None:
    """Si otro proceso (simulador, maqueta IoT…) reescribe el JSON, la siguiente lectura lo ve."""
    path = data_dir / 'sensores.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    document['sensores'][0]['valor'] = 31.5
    path.write_text(json.dumps(document), encoding='utf-8')
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))  # garantiza una fecha distinta

    sensor = repositories.sensors.get('temp-tienda')
    assert sensor is not None and sensor.value == 31.5


def test_writes_keep_other_keys(data_dir: Path, repositories: Repositories) -> None:
    sensor = repositories.sensors.get('temp-tienda')
    assert sensor is not None
    repositories.sensors.update(sensor)
    document = json.loads((data_dir / 'sensores.json').read_text(encoding='utf-8'))
    assert 'camaras' in document  # guardar sensores no borra las cámaras del mismo fichero


def test_invalid_json_keeps_last_valid_version(tmp_path: Path) -> None:
    path = tmp_path / 'datos.json'
    path.write_text('{"lista": [1, 2]}', encoding='utf-8')
    file = JsonFile(path)
    assert file.read() == {'lista': [1, 2]}

    path.write_text('{"lista": [1, ', encoding='utf-8')  # escritura a medias de otro proceso
    assert file.read() == {'lista': [1, 2]}


def test_persistent_invalid_json_is_reported(tmp_path: Path) -> None:
    """Pasado el periodo de gracia, un fichero que sigue roto deja de ocultarse."""
    path = tmp_path / 'datos.json'
    path.write_text('{"lista": [1, 2]}', encoding='utf-8')
    file = JsonFile(path, grace_seconds=0.0)
    file.read()
    path.write_text('{"lista": [1, ', encoding='utf-8')
    assert file.read() == {'lista': [1, 2]}  # primera lectura fallida: aún dentro del periodo de gracia
    with pytest.raises(DataFormatError, match='JSON no válido'):
        file.read()


def test_invalid_json_without_previous_version_fails(tmp_path: Path) -> None:
    path = tmp_path / 'roto.json'
    path.write_text('no es json', encoding='utf-8')
    with pytest.raises(DataFormatError, match=r'roto\.json'):
        JsonFile(path).read()


def test_record_errors_point_to_the_field() -> None:
    record = Record({'valor': 'alto'}, 'sensores.json › sensores[3]')
    with pytest.raises(DataFormatError, match=r'sensores\[3\].*«valor» debe ser numérico'):
        record.number('valor')
    with pytest.raises(DataFormatError, match='«estado» debe ser uno de'):
        Record({'estado': 'roto'}, 'x').choice('estado', SensorStatus)
    with pytest.raises(DataFormatError, match='«fecha_hora» es obligatorio'):
        Record({}, 'x').timestamp('fecha_hora')


def test_record_converts_timezones_to_local_time() -> None:
    moment = Record({'fecha_hora': '2026-10-14T12:30:00+00:00'}, 'x').timestamp('fecha_hora')
    assert moment.tzinfo is None
    assert moment == datetime.fromisoformat('2026-10-14T12:30:00+00:00').astimezone().replace(tzinfo=None)


def test_history_readings_keep_their_variable_and_day(repositories: Repositories) -> None:
    readings = repositories.readings.list_all()
    assert {reading.metric for reading in readings} == set(Metric)
    assert {reading.day.isoformat() for reading in readings} == {'2026-10-13', '2026-10-14'}
    occupancy_today = [
        reading.value for reading in readings
        if reading.metric is Metric.OCCUPANCY and reading.day.isoformat() == '2026-10-14'
    ]
    assert occupancy_today == [30, 54, 110, 94, 72, 86]


def test_writes_never_use_the_last_valid_version(tmp_path: Path) -> None:
    path = tmp_path / 'datos.json'
    data = JsonFile(path, grace_seconds=60)
    data.write({'valor': 1})
    path.write_text('{"valor": ', encoding='utf-8')  # otro proceso lo está escribiendo
    assert data.read() == {'valor': 1}  # la interfaz sigue mostrando la última versión válida…
    with pytest.raises(DataFormatError):
        data.read(strict=True)  # …pero nada se guarda encima de ella


def test_changes_are_not_saved_over_a_half_written_file(data_dir: Path, repositories: Repositories) -> None:
    alert = repositories.alerts.list_all()[0]
    path = data_dir / 'alertas.json'
    path.write_text('{"alertas": [', encoding='utf-8')
    with pytest.raises(DataFormatError):
        repositories.alerts.update(alert)
    assert path.read_text(encoding='utf-8') == '{"alertas": ['
