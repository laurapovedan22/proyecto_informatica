"""Datos en vivo: la aplicación simula lecturas continuas y verosímiles sin abrir ninguna ventana."""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from statistics import mean
from threading import Event, get_ident
from unittest.mock import Mock

import pytest
from jsonschema import Draft202012Validator

from lumina.app import BackgroundCycle, LuminaApp
from lumina.controllers import FixedClock, LiveSimulator, Services
from lumina.models import ActuatorMode, AlertType, Sensor, SensorStatus, SensorType
from lumina.repositories import DataFormatError, Repositories
from lumina.settings import AppSettings
from scripts.simular_sensores import SensorSimulator

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def simulator(repositories: Repositories, clock: FixedClock, seed: int = 7) -> LiveSimulator:
    return LiveSimulator(repositories, clock, rng=random.Random(seed))


def sensor(repositories: Repositories, sensor_id: str) -> Sensor:
    found = repositories.sensors.get(sensor_id)
    assert found is not None
    return found


def run(live: LiveSimulator, clock: FixedClock, cycles: int, seconds: float) -> list[list[Sensor]]:
    """Ejecuta varios ciclos avanzando el reloj y devuelve los sensores tras cada uno."""
    history: list[list[Sensor]] = []
    for _ in range(cycles):
        clock.advance(timedelta(seconds=seconds))
        live.step(seconds)
        history.append(live._repositories.sensors.list_all())
    return history


def test_each_cycle_renews_every_operational_reading(
    repositories: Repositories, clock: FixedClock, data_dir: Path
) -> None:
    schema = json.loads((PROJECT_ROOT / 'schemas' / 'sensores.schema.json').read_text(encoding='utf-8'))
    before = json.loads((data_dir / 'sensores.json').read_text(encoding='utf-8'))
    saved = simulator(repositories, clock).step()
    document = json.loads((data_dir / 'sensores.json').read_text(encoding='utf-8'))
    assert list(Draft202012Validator(schema).iter_errors(document)) == []
    assert document['camaras'] == before['camaras']  # solo escribe sensores
    assert {reading.id for reading in saved} == {item['id'] for item in before['sensores']}
    assert all(reading.updated_at == clock.now() for reading in repositories.sensors.list_all())


def test_live_values_vary_and_stay_realistic(repositories: Repositories, clock: FixedClock) -> None:
    history = run(simulator(repositories, clock), clock, cycles=120, seconds=60)  # dos horas simuladas
    series: dict[str, list[float]] = {}
    for sensors in history:
        for item in sensors:
            assert item.value is not None
            series.setdefault(item.id, []).append(item.value)
    for sensor_id, values in series.items():
        assert len(set(values)) > (1 if sensor_id.startswith('mov-') else 3), f'{sensor_id} no cambia'
    assert all(21.0 <= value <= 26.0 for value in series['temp-tienda'])
    assert all(17.0 <= value <= 22.5 for value in series['temp-almacen'])
    assert all(35.0 <= value <= 61.0 for value in series['hum-tienda'])
    assert all(0 <= value <= 150 and value.is_integer() for value in series['aforo-tienda'])
    assert all(0 <= value <= 50 and value.is_integer() for value in series['vehiculos-parking'])
    assert all(35 <= value <= 95 or 170 <= value <= 195 for value in series['dist-acceso-parking'])
    assert any(value < 100 for value in series['dist-acceso-parking'])  # han pasado coches
    for motion in ('mov-almacen', 'mov-salida-emergencia', 'mov-puerta-personal'):
        assert set(series[motion]) == {0.0, 1.0}
        assert mean(series[motion]) < 0.5  # detecciones esporádicas, no continuas


def test_counters_follow_the_hour_and_never_exceed_the_capacity(repositories: Repositories) -> None:
    assert LiveSimulator.store_crowd(19.5) > LiveSimulator.store_crowd(13) > LiveSimulator.store_crowd(3)
    assert LiveSimulator.parking_crowd(12.5) > LiveSimulator.parking_crowd(3)
    averages = []
    for start in (datetime(2026, 10, 14, 3), datetime(2026, 10, 14, 19)):
        clock = FixedClock(start)
        repositories.sensors.modify('aforo-tienda', lambda current: replace(current, value=86))
        history = run(simulator(repositories, clock), clock, cycles=60, seconds=60)
        counts = [item.value or 0 for sensors in history for item in sensors if item.id == 'aforo-tienda']
        averages.append(mean(counts))
    assert averages[1] > averages[0] + 20  # más clientes por la tarde que de madrugada

    repositories.config.save(replace(repositories.config.load(), max_occupancy=0, parking_spaces=10))
    repositories.sensors.modify('vehiculos-parking', lambda current: replace(current, value=999))
    clock = FixedClock(datetime(2026, 10, 14, 14, 30))
    for sensors in run(simulator(repositories, clock), clock, cycles=10, seconds=5):
        values = {item.id: item.value for item in sensors}
        assert values['aforo-tienda'] == 0
        assert values['vehiculos-parking'] is not None and 0 <= values['vehiculos-parking'] <= 10


def test_missing_failed_and_stale_readings_are_left_alone(repositories: Repositories, clock: FixedClock) -> None:
    repositories.sensors.modify('temp-tienda', lambda current: replace(current, value=None))
    repositories.sensors.modify('hum-tienda', lambda current: replace(current, status=SensorStatus.ERROR))
    repositories.sensors.modify('temp-almacen', lambda current: replace(current, status=SensorStatus.STALE))
    repositories.sensors.modify('aforo-tienda', lambda current: replace(current, value=float('nan')))
    before = {item.id: item for item in repositories.sensors.list_all()}
    run(simulator(repositories, clock), clock, cycles=3, seconds=5)
    after = {item.id: item for item in repositories.sensors.list_all()}
    for sensor_id in ('temp-tienda', 'hum-tienda', 'temp-almacen'):
        assert after[sensor_id] == before[sensor_id]
    assert after['aforo-tienda'].updated_at == before['aforo-tienda'].updated_at
    assert after['vehiculos-parking'].updated_at == clock.now()


def test_an_external_source_takes_over_a_sensor(repositories: Repositories, clock: FixedClock) -> None:
    """La maqueta IoT o los escenarios del simulador de terminal mandan sobre la simulación."""
    live = simulator(repositories, clock)
    live.step()
    repositories.sensors.modify('temp-tienda', lambda current: replace(current, value=27.0, updated_at=clock.now()))
    for _ in range(3):  # durante dos minutos desde su última escritura, el simulador no lo toca
        clock.advance(timedelta(seconds=30))
        live.step()
        assert sensor(repositories, 'temp-tienda').value == 27.0
        assert sensor(repositories, 'hum-tienda').updated_at == clock.now()  # el resto sigue vivo

    clock.advance(LiveSimulator.EXTERNAL_HOLD)
    live.step()
    resumed = sensor(repositories, 'temp-tienda')
    assert resumed.updated_at == clock.now() and resumed.value != 27.0

    for _ in range(4):  # una fuente que informa en cada ciclo (con su hora) conserva siempre el control
        clock.advance(timedelta(seconds=60))
        repositories.sensors.modify(
            'vehiculos-parking', lambda current: replace(current, value=40, updated_at=clock.now())
        )
        live.step()
        assert sensor(repositories, 'vehiculos-parking').value == 40


def test_motion_detections_are_brief(repositories: Repositories, clock: FixedClock) -> None:
    class FrequentMotion(LiveSimulator):
        MOTION_GAP_SECONDS = 30.0

    assert sensor(repositories, 'mov-almacen').value == 1.0  # detección en curso en los datos de ejemplo
    history = run(FrequentMotion(repositories, clock, rng=random.Random(3)), clock, cycles=60, seconds=5)
    almacen = [next(item.value for item in sensors if item.id == 'mov-almacen') for sensors in history]
    assert almacen[9:].count(0.0) > 0  # la detección inicial termina en menos de un minuto
    starts = sum(1 for before, after in pairwise(almacen) if (before, after) == (0.0, 1.0))
    assert starts >= 2  # y aparecen otras nuevas


def test_the_simulation_never_overwrites_an_incomplete_file(
    repositories: Repositories, clock: FixedClock, data_dir: Path
) -> None:
    live = simulator(repositories, clock)
    live.step()
    path = data_dir / 'sensores.json'
    path.write_text('{"sensores": [', encoding='utf-8')
    with pytest.raises(DataFormatError):
        live.step()
    assert path.read_text(encoding='utf-8') == '{"sensores": ['
    with pytest.raises(ValueError, match='positiva'):
        live.step(0)


def test_the_simulation_needs_live_refreshes(services: Services) -> None:
    assert LuminaApp(AppSettings(), services=services).simulates
    assert not LuminaApp(AppSettings(simulation=False), services=services).simulates
    assert not LuminaApp(AppSettings(refresh_seconds=0), services=services).simulates
    assert AppSettings.from_env({'LUMINA_SIMULATION': 'false'}).simulation is False
    assert AppSettings.from_env({}).simulation is True


async def test_background_cycle_runs_in_a_thread_and_waits_on_shutdown() -> None:
    started, release = Event(), Event()
    loop_thread = get_ident()

    def job() -> None:
        assert get_ident() != loop_thread  # no bloquea el bucle de eventos de la interfaz
        started.set()
        assert release.wait(timeout=5)

    cycle = BackgroundCycle('prueba', job)
    timer = Mock()
    cycle._timer = timer
    running = asyncio.create_task(cycle.run())
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        await cycle.run()  # nunca se solapan dos ciclos
        stopping = asyncio.create_task(cycle.stop())
        await asyncio.sleep(0)
        timer.cancel.assert_called_once()
        assert not stopping.done()  # espera la escritura en curso
    finally:
        release.set()
        await running
    await stopping
    started.clear()
    await cycle.run()
    assert not started.is_set()  # después de cerrar no empieza ningún ciclo


async def test_background_cycle_retries_after_an_unexpected_error() -> None:
    job = Mock(side_effect=[RuntimeError('fallo inesperado'), None])
    cycle = BackgroundCycle('prueba', job)
    await cycle.run()
    await cycle.run()
    assert job.call_count == 2


def test_sensor_types_are_all_simulated() -> None:
    """Si se añade un tipo de sensor, el simulador debe decidir cómo varía."""
    assert {member.value for member in SensorType} == {
        'temperatura', 'humedad', 'movimiento', 'distancia', 'contador_personas', 'contador_vehiculos',
    }


# --- Sprint 3: las reglas evalúan las lecturas vivas como las de la maqueta -------------------


def test_demo_scenarios_keep_priority_over_the_live_simulation(
    services: Services, repositories: Repositories, clock: FixedClock
) -> None:
    """``--escenario critica`` o ``calor`` siguen funcionando aunque la aplicación esté simulando."""
    scenarios = SensorSimulator(repositories, clock, random.Random(1))
    services.simulation.step()
    scenarios.scenario('critica')
    clock.advance(timedelta(seconds=5))
    services.simulation.step()  # no toca lo que acaba de escribir el escenario
    created = services.rules.evaluate().alerts_created
    critical = {alert.sensor_id for alert in created if alert.type is AlertType.CRITICAL_TEMPERATURE}
    assert critical == {'temp-tienda', 'temp-almacen'}

    scenarios.scenario('calor')
    services.supervision.set_automatic('ventilador-tienda', services.users.get('usr-carlos'))
    clock.advance(timedelta(seconds=30))
    services.simulation.step()
    services.rules.evaluate()
    fan = repositories.actuators.get('ventilador-tienda')
    assert fan is not None and fan.is_on and fan.mode is ActuatorMode.AUTOMATIC  # umbral + 1 °C


def test_live_motion_in_a_restricted_zone_raises_a_single_alert(
    services: Services, repositories: Repositories, clock: FixedClock
) -> None:
    class FrequentMotion(LiveSimulator):
        MOTION_GAP_SECONDS = 10.0

    live = FrequentMotion(repositories, clock, rng=random.Random(5))
    created: list[str] = []
    for _ in range(40):
        clock.advance(timedelta(seconds=5))
        live.step()
        created += [alert.sensor_id or '' for alert in services.rules.evaluate().alerts_created]
    assert 'mov-salida-emergencia' in created and 'mov-puerta-personal' in created
    assert len(created) == len(set(created))  # una sola alerta abierta por sensor, aunque se repita la detección
    assert 'mov-almacen' not in created  # ya tenía una alerta abierta en los datos de ejemplo
