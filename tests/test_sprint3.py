"""Aceptación de H3.1–H3.4: reglas, persistencia atómica, permisos y contratos JSON."""

from __future__ import annotations

import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from typing import Any
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

from lumina.controllers import (
    ConfigurationChanges,
    FixedClock,
    PermissionDeniedError,
    RulesController,
    Services,
    ValidationError,
)
from lumina.models import ActuatorMode, AlertStatus, AlertType, Role, Sensor, SensorStatus, SensorType, User
from lumina.repositories import DataFormatError, Repositories
from scripts.simular_sensores import SensorSimulator

ROOT = Path(__file__).resolve().parent.parent


def changes(services: Services) -> ConfigurationChanges:
    """Copia editable de los parámetros vigentes."""
    config = services.configuration.current()
    return ConfigurationChanges(
        config.fan_threshold,
        config.critical_temperature,
        config.max_occupancy,
        config.parking_spaces,
        config.max_reading_age_minutes,
        frozenset(zone.id for zone in config.zones if zone.restricted),
    )


def temperature(repositories: Repositories, value: float) -> None:
    repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, value=value))


def test_configuration_saves_valid_changes_and_immediately_uses_them(
    services: Services,
    repositories: Repositories,
    admin: User,
) -> None:
    services.supervision.set_automatic('ventilador-tienda', admin)
    updated = services.configuration.update(
        replace(
            changes(services),
            fan_threshold=22,
            critical_temperature=23.5,
            max_occupancy=200,
            parking_spaces=70,
            max_reading_age_minutes=10,
            restricted_zone_ids=frozenset({'parking'}),
        ),
        admin,
    )
    assert repositories.config.load() == updated
    assert updated.max_occupancy == 200 and updated.parking_spaces == 70
    assert updated.max_reading_age_minutes == 10
    assert {zone.id for zone in updated.zones if zone.restricted} == {'parking'}
    fan = repositories.actuators.get('ventilador-tienda')
    assert fan is not None and fan.is_on
    assert any(item.alert.type is AlertType.CRITICAL_TEMPERATURE for item in services.supervision.open_alerts())


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('fan_threshold', float('nan')),
        ('critical_temperature', float('inf')),
        ('critical_temperature', 26),
        ('fan_threshold', 61),
        ('critical_temperature', -11),
        ('max_occupancy', 0),
        ('parking_spaces', -1),
        ('max_occupancy', 1.5),
        ('parking_spaces', True),
        ('max_reading_age_minutes', -1),
        ('max_reading_age_minutes', 1441),
        ('max_reading_age_minutes', 1.5),
        ('restricted_zone_ids', frozenset({'inexistente'})),
    ],
)
def test_configuration_rejects_invalid_changes_without_writing(
    services: Services,
    admin: User,
    data_dir: Path,
    field: str,
    value: Any,
) -> None:
    before = (data_dir / 'configuracion.json').read_bytes()
    with pytest.raises(ValidationError):
        services.configuration.update(replace(changes(services), **{field: value}), admin)
    assert (data_dir / 'configuracion.json').read_bytes() == before


def test_configuration_validates_temperatures_after_rounding(services: Services, admin: User) -> None:
    with pytest.raises(ValidationError):
        services.configuration.update(
            replace(changes(services), fan_threshold=26.01, critical_temperature=26.02), admin
        )


@pytest.mark.parametrize('actor_id', ['usr-carlos', 'usr-marta'])
def test_only_admin_can_configure(services: Services, repositories: Repositories, actor_id: str) -> None:
    actor = repositories.users.get(actor_id)
    assert actor is not None
    with pytest.raises(PermissionDeniedError):
        services.configuration.update(changes(services), actor)


def test_rules_reread_thresholds_and_restricted_zones(services: Services, repositories: Repositories) -> None:
    for alert in repositories.alerts.list_all():
        repositories.alerts.delete(alert.id)
    repositories.config.modify(
        lambda config: replace(
            config,
            fan_threshold=22,
            critical_temperature=23,
            zones=tuple(replace(zone, restricted=False) for zone in config.zones),
        )
    )
    result = services.rules.evaluate()
    assert [alert.type for alert in result.alerts_created] == [AlertType.CRITICAL_TEMPERATURE]
    repositories.config.modify(
        lambda config: replace(
            config,
            critical_temperature=60,
            zones=tuple(replace(zone, restricted=zone.id == 'almacen') for zone in config.zones),
        )
    )
    assert [alert.type for alert in services.rules.evaluate().alerts_created] == [AlertType.RESTRICTED_MOTION]
    assert not services.rules.evaluate().alerts_created


@pytest.mark.parametrize('status', [AlertStatus.PENDING, AlertStatus.IN_REVIEW])
def test_rules_do_not_duplicate_open_alerts(
    services: Services,
    repositories: Repositories,
    status: AlertStatus,
) -> None:
    repositories.alerts.modify('alr-0002', lambda alert: replace(alert, status=status))
    assert services.rules.evaluate().alerts_created == ()


def test_simultaneous_evaluations_use_atomic_add_check(
    data_dir: Path, repositories: Repositories, clock: FixedClock
) -> None:
    temperature(repositories, 30)
    barrier = Barrier(2)

    def evaluate(_: int) -> int:
        controller = RulesController(Repositories.from_json_dir(data_dir), clock)
        barrier.wait(timeout=5)
        return len(controller.evaluate().alerts_created)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(evaluate, range(2))) == 1
    critical = [alert for alert in repositories.alerts.list_all() if alert.type is AlertType.CRITICAL_TEMPERATURE]
    assert len(critical) == 1
    assert critical[0].sensor_id == 'temp-tienda' and critical[0].zone_id == 'tienda'
    assert critical[0].created_at == clock.now()


def test_alert_deduplication_key_includes_type_zone_and_sensor(services: Services, repositories: Repositories) -> None:
    temperature(repositories, 30)
    assert len(services.rules.evaluate().alerts_created) == 1
    repositories.sensors.add(Sensor('temp-extra', 'Temperatura extra', SensorType.TEMPERATURE, 'tienda', 30))
    assert len(services.rules.evaluate().alerts_created) == 1
    repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, zone_id='almacen'))
    assert len(services.rules.evaluate().alerts_created) == 1
    repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, status=SensorStatus.ERROR))
    assert [alert.type for alert in services.rules.evaluate().alerts_created] == [AlertType.SENSOR_FAILURE]


def test_sensor_error_with_no_value_generates_failure(services: Services, repositories: Repositories) -> None:
    repositories.sensors.modify('hum-tienda', lambda sensor: replace(sensor, value=None, status=SensorStatus.ERROR))
    result = services.rules.evaluate()
    assert len(result.alerts_created) == 1
    assert result.alerts_created[0].type is AlertType.SENSOR_FAILURE
    assert result.alerts_created[0].sensor_id == 'hum-tienda'


def test_restricted_motion_activates_led_alarm_even_with_existing_alert(
    services: Services,
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    for identifier in ('led-aviso', 'alarma-digital'):
        repositories.actuators.modify(identifier, lambda item: replace(item, is_on=False, mode=ActuatorMode.MANUAL))
    result = services.rules.evaluate()
    assert result.alerts_created == ()
    assert {item.id for item in result.actuators_changed} == {'led-aviso', 'alarma-digital'}
    assert all(item.is_on and item.mode is ActuatorMode.AUTOMATIC for item in result.actuators_changed)
    assert all(item.updated_at == clock.now() for item in result.actuators_changed)
    assert services.rules.evaluate().actuators_changed == ()


def test_automatic_fan_hysteresis_and_manual_override(
    services: Services,
    repositories: Repositories,
    security: User,
) -> None:
    services.supervision.set_actuator('ventilador-tienda', False, security)
    temperature(repositories, 27)
    assert not services.rules.evaluate().actuators_changed
    automatic = services.supervision.set_automatic('ventilador-tienda', security)
    assert automatic.is_on and automatic.mode is ActuatorMode.AUTOMATIC
    for value, expected in ((26, True), (25.6, True), (25.5, False), (26, False), (26.1, True)):
        temperature(repositories, value)
        services.rules.evaluate()
        fan = repositories.actuators.get('ventilador-tienda')
        assert fan is not None and fan.is_on is expected
    manual = services.supervision.set_actuator('ventilador-tienda', True, security)
    assert manual.mode is ActuatorMode.MANUAL
    temperature(repositories, 18)
    services.rules.evaluate()
    assert repositories.actuators.get('ventilador-tienda') == manual
    assert not services.supervision.set_automatic('ventilador-tienda', security).is_on


def test_fan_uses_hottest_operational_sensor_in_its_zone(
    services: Services,
    repositories: Repositories,
    security: User,
) -> None:
    repositories.sensors.add(Sensor('temp-extra', 'Sensor extra', SensorType.TEMPERATURE, 'tienda', 28))
    assert services.supervision.set_automatic('ventilador-tienda', security).is_on
    repositories.sensors.modify('temp-extra', lambda sensor: replace(sensor, status=SensorStatus.ERROR))
    services.rules.evaluate()
    fan = repositories.actuators.get('ventilador-tienda')
    assert fan is not None and not fan.is_on


@pytest.mark.parametrize('invalid', ['error', 'ausente', 'antigua'])
def test_invalid_readings_do_not_drive_fan_or_motion(
    services: Services,
    repositories: Repositories,
    security: User,
    clock: FixedClock,
    invalid: str,
) -> None:
    temperature(repositories, 28)
    fan = services.supervision.set_automatic('ventilador-tienda', security)
    for sensor_id in ('temp-tienda', 'mov-almacen'):
        if invalid == 'error':
            repositories.sensors.modify(sensor_id, lambda sensor: replace(sensor, status=SensorStatus.ERROR))
        elif invalid == 'ausente':
            repositories.sensors.modify(sensor_id, lambda sensor: replace(sensor, value=None))
        else:
            repositories.config.modify(lambda config: replace(config, max_reading_age_minutes=1))
            clock.advance(timedelta(minutes=2))
    assert services.rules.evaluate().actuators_changed == ()
    assert repositories.actuators.get(fan.id) == fan


def test_alert_changes_keep_original_details_and_current_responsible(
    services: Services,
    repositories: Repositories,
    security: User,
    admin: User,
    clock: FixedClock,
) -> None:
    original = repositories.alerts.get('alr-0002')
    assert original is not None
    reviewed = services.supervision.update_alert(original.id, AlertStatus.IN_REVIEW, security)
    assert reviewed.handled_by == security.name and reviewed.updated_at == clock.now()
    clock.advance(timedelta(minutes=1))
    resolved = services.supervision.update_alert(original.id, AlertStatus.RESOLVED, admin)
    assert resolved.handled_by == admin.name and resolved.updated_at == clock.now()
    assert (resolved.type, resolved.zone_id, resolved.created_at, resolved.sensor_id, resolved.description) == (
        original.type,
        original.zone_id,
        original.created_at,
        original.sensor_id,
        original.description,
    )
    assert services.supervision.update_alert(original.id, AlertStatus.RESOLVED, security) == resolved
    with pytest.raises(ValidationError):
        services.supervision.update_alert(original.id, AlertStatus.IN_REVIEW, security)
    new = services.rules.evaluate().alerts_created
    assert len(new) == 1 and new[0].id != original.id
    assert repositories.alerts.get(original.id) == resolved


def test_manager_cannot_use_any_control(services: Services, manager: User) -> None:
    with pytest.raises(PermissionDeniedError):
        services.supervision.set_actuator('ventilador-tienda', False, manager)
    with pytest.raises(PermissionDeniedError):
        services.supervision.set_automatic('ventilador-tienda', manager)
    with pytest.raises(PermissionDeniedError):
        services.supervision.update_alert('alr-0002', AlertStatus.RESOLVED, manager)


@pytest.mark.parametrize('action', ['configuracion', 'alerta', 'equipo', 'automatico'])
def test_permissions_are_checked_again_inside_transaction(
    services: Services,
    repositories: Repositories,
    admin: User,
    action: str,
) -> None:
    target = (
        repositories.config
        if action == 'configuracion'
        else (repositories.alerts if action == 'alerta' else repositories.actuators)
    )
    original = target.modify

    def revoke() -> bool:
        repositories.users.modify(admin.id, lambda account: replace(account, role=Role.MANAGER))
        return True

    with patch.object(target, 'modify', wraps=original) as transaction:
        transaction.side_effect = lambda *args, **kwargs: (revoke(), original(*args, **kwargs))[1]
        with pytest.raises(PermissionDeniedError):
            if action == 'configuracion':
                services.configuration.update(changes(services), admin)
            elif action == 'alerta':
                services.supervision.update_alert('alr-0002', AlertStatus.RESOLVED, admin)
            elif action == 'equipo':
                services.supervision.set_actuator('ventilador-tienda', False, admin)
            else:
                services.supervision.set_automatic('ventilador-tienda', admin)


def test_configuration_strict_read_does_not_overwrite_corruption(
    services: Services,
    admin: User,
    data_dir: Path,
) -> None:
    draft = changes(services)
    path = data_dir / 'configuracion.json'
    path.write_text('{incompleto', encoding='utf-8')
    with pytest.raises(DataFormatError):
        services.configuration.update(draft, admin)
    assert path.read_text(encoding='utf-8') == '{incompleto'


@pytest.mark.parametrize('scenario', ['calor', 'critica', 'movimiento', 'normal', 'fallo'])
def test_sprint_three_writes_follow_schemas(
    services: Services,
    repositories: Repositories,
    clock: FixedClock,
    admin: User,
    data_dir: Path,
    scenario: str,
) -> None:
    services.configuration.update(changes(services), admin)
    services.supervision.set_automatic('ventilador-tienda', admin)
    simulator = SensorSimulator(repositories, clock, random.Random(7))
    assert simulator.scenario(scenario)
    services.rules.evaluate()
    services.supervision.set_actuator('led-aviso', False, admin)
    services.supervision.update_alert('alr-0002', AlertStatus.IN_REVIEW, admin)
    services.supervision.update_alert('alr-0002', AlertStatus.RESOLVED, admin)
    for name in ('sensores', 'configuracion', 'alertas', 'actuadores'):
        schema = json.loads((ROOT / 'schemas' / f'{name}.schema.json').read_text(encoding='utf-8'))
        document = json.loads((data_dir / f'{name}.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(document)


def test_rules_refuse_invalid_current_configuration_without_side_effects(
    services: Services, data_dir: Path,
) -> None:
    services.rules.evaluate()
    before = [(data_dir / name).read_bytes() for name in ('alertas.json', 'actuadores.json')]
    (data_dir / 'configuracion.json').write_text('{incompleto', encoding='utf-8')
    with pytest.raises(DataFormatError):
        services.rules.evaluate()
    assert [(data_dir / name).read_bytes() for name in ('alertas.json', 'actuadores.json')] == before


@pytest.mark.parametrize('action', ['alerta', 'equipo'])
def test_alert_and_actuator_changes_never_overwrite_corrupt_files(
    services: Services, security: User, data_dir: Path, action: str,
) -> None:
    path = data_dir / ('alertas.json' if action == 'alerta' else 'actuadores.json')
    services.supervision.snapshot()
    path.write_text('{incompleto', encoding='utf-8')
    with pytest.raises(DataFormatError):
        if action == 'alerta':
            services.supervision.update_alert('alr-0002', AlertStatus.RESOLVED, security)
        else:
            services.supervision.set_actuator('ventilador-tienda', False, security)
    assert path.read_text(encoding='utf-8') == '{incompleto'


@pytest.mark.parametrize('account_state', ['desactivada', 'eliminada'])
def test_old_actor_cannot_act_after_losing_access(
    services: Services, repositories: Repositories, security: User, account_state: str,
) -> None:
    if account_state == 'desactivada':
        repositories.users.modify(security.id, lambda account: replace(account, active=False))
    else:
        repositories.users.delete(security.id)
    with pytest.raises(PermissionDeniedError):
        services.supervision.update_alert('alr-0002', AlertStatus.RESOLVED, security)
    with pytest.raises(PermissionDeniedError):
        services.supervision.set_actuator('led-aviso', False, security)


def test_alert_uses_current_responsible_name(services: Services, repositories: Repositories, security: User) -> None:
    repositories.users.modify(security.id, lambda account: replace(account, name='Carlos Ruiz García'))
    alert = services.supervision.update_alert('alr-0002', AlertStatus.IN_REVIEW, security)
    assert alert.handled_by == 'Carlos Ruiz García'


@pytest.mark.parametrize('scenario', ['calor', 'critica', 'movimiento', 'normal', 'fallo'])
def test_demo_scenario_cli_terminates_and_only_writes_sensors(data_dir: Path, scenario: str) -> None:
    unchanged = {
        path.name: path.read_bytes() for path in data_dir.glob('*.json') if path.name != 'sensores.json'
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'simular_sensores.py'), '--datos', str(data_dir),
         '--escenario', scenario],
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert f'Escenario {scenario}:' in result.stdout
    assert {name: (data_dir / name).read_bytes() for name in unchanged} == unchanged


@pytest.mark.parametrize(
    ('field', 'value'),
    [('umbral_temperatura', float('nan')), ('temperatura_critica', float('inf')),
     ('umbral_temperatura', 61), ('temperatura_critica', -11), ('temperatura_critica', 26)],
)
def test_rules_reject_malformed_thresholds_without_side_effects(
    services: Services, data_dir: Path, field: str, value: float,
) -> None:
    path = data_dir / 'configuracion.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    document[field] = value
    path.write_text(json.dumps(document), encoding='utf-8')
    before = [(data_dir / name).read_bytes() for name in ('alertas.json', 'actuadores.json')]
    with pytest.raises(DataFormatError):
        services.rules.evaluate()
    assert [(data_dir / name).read_bytes() for name in ('alertas.json', 'actuadores.json')] == before


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_sensor_generates_failure_without_driving_fan(
    services: Services, repositories: Repositories, value: float,
) -> None:
    repositories.actuators.modify('ventilador-tienda', lambda item: replace(item, mode=ActuatorMode.AUTOMATIC))
    temperature(repositories, value)
    before = repositories.actuators.get('ventilador-tienda')
    result = services.rules.evaluate()
    assert [alert.type for alert in result.alerts_created] == [AlertType.SENSOR_FAILURE]
    assert result.alerts_created[0].sensor_id == 'temp-tienda'
    assert repositories.actuators.get('ventilador-tienda') == before


def test_configuration_transactions_share_path_lock_and_are_reentrant(data_dir: Path) -> None:
    barrier = Barrier(2)

    def increment(_: int) -> None:
        repository = Repositories.from_json_dir(data_dir / '..' / data_dir.name).config
        barrier.wait(timeout=5)
        for _ in range(20):
            repository.modify(lambda config: replace(config, max_occupancy=config.max_occupancy + 1))

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(increment, range(2)))
    assert Repositories.from_json_dir(data_dir).config.load().max_occupancy == 190


def test_simultaneous_alert_actions_keep_resolution_and_responsible(
    services: Services, repositories: Repositories, security: User, admin: User,
) -> None:
    barrier = Barrier(2)

    def update(review: bool) -> None:
        barrier.wait(timeout=5)
        try:
            services.supervision.update_alert(
                'alr-0002', AlertStatus.IN_REVIEW if review else AlertStatus.RESOLVED, security if review else admin,
            )
        except ValidationError:
            assert review  # resolver antes de revisar impide reabrir la alerta

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(update, (True, False)))
    current = repositories.alerts.get('alr-0002')
    assert current is not None and current.status is AlertStatus.RESOLVED and current.handled_by == admin.name


@pytest.mark.parametrize('ending', ['sin_movimiento', 'zona_no_restringida'])
def test_motion_warning_stays_latched_until_manual_switch_off(
    services: Services, repositories: Repositories, security: User, ending: str,
) -> None:
    services.rules.evaluate()
    if ending == 'sin_movimiento':
        repositories.sensors.modify('mov-almacen', lambda sensor: replace(sensor, value=0))
    else:
        repositories.config.modify(
            lambda config: replace(config, zones=tuple(replace(zone, restricted=False) for zone in config.zones))
        )
    services.rules.evaluate()
    for identifier in ('led-aviso', 'alarma-digital'):
        current = repositories.actuators.get(identifier)
        assert current is not None and current.is_on and current.mode is ActuatorMode.AUTOMATIC
        services.supervision.set_actuator(identifier, False, security)
    services.rules.evaluate()
    for identifier in ('led-aviso', 'alarma-digital'):
        current = repositories.actuators.get(identifier)
        assert current is not None and not current.is_on and current.mode is ActuatorMode.MANUAL
    alert = repositories.alerts.get('alr-0002')
    assert alert is not None and alert.is_open  # cesar la causa no sustituye la atención de la incidencia
