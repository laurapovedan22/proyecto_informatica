"""Aceptación de las pantallas del Sprint 3 con la simulación de usuario de NiceGUI."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident
from unittest.mock import patch

import pytest
from nicegui import app, ui
from nicegui.testing import User, user_simulation
from test_supervision_ui import LOGIN_RETRIES, MAIN_FILE, enter

from lumina.controllers import RulesController, RulesResult, Services
from lumina.models import ActuatorMode, AlertStatus, AlertType, Role
from lumina.repositories import Repositories
from lumina.views.components.shell import AlertWatcher
from lumina.views.pages.configuration import ConfigurationPage


async def test_admin_configuration_form_saves_and_rules_apply(user: User, repositories: Repositories) -> None:
    await enter(user, 'admin')
    await user.open('/configuracion')
    await user.should_see('Zonas restringidas')
    user.find(marker='config-fan').clear().type('22')
    user.find(marker='config-critical').clear().type('23.5')
    user.find(marker='config-occupancy').clear().type('180')
    user.find(marker='config-parking').clear().type('60')
    user.find(marker='config-age').clear().type('0')
    user.find(marker='zone-almacen').click()
    user.find('Guardar configuración').click()
    await user.should_see('Configuración guardada.')
    config = repositories.config.load()
    assert (config.fan_threshold, config.critical_temperature, config.max_occupancy, config.parking_spaces) == (
        22,
        23.5,
        180,
        60,
    )
    assert not next(zone for zone in config.zones if zone.id == 'almacen').restricted
    assert any(alert.type is AlertType.CRITICAL_TEMPERATURE for alert in repositories.alerts.list_all())


async def test_invalid_configuration_stays_unsaved(user: User, repositories: Repositories) -> None:
    await enter(user, 'admin')
    await user.open('/configuracion')
    previous = repositories.config.load()
    user.find(marker='config-critical').clear().type('25')
    user.find('Guardar configuración').click()
    await user.should_see('La temperatura crítica debe ser mayor que el umbral del ventilador.')
    assert repositories.config.load() == previous


@pytest.mark.parametrize('role', ['seguridad', 'gerente'])
async def test_configuration_route_is_admin_only(user: User, role: str) -> None:
    await enter(user, role)
    await user.should_not_see('Configuración')
    await user.open('/configuracion')
    await user.should_see('Tu cuenta')
    await user.should_not_see('Guardar configuración')


@pytest.mark.parametrize('role', ['seguridad', 'admin'])
async def test_alert_details_review_resolution_and_equipment_controls(
    user: User,
    repositories: Repositories,
    role: str,
) -> None:
    await enter(user, role)
    await user.should_see('1 alerta pendiente')
    await user.should_see('Estado de los equipos')
    await user.open('/supervision')
    with user.scope(marker='alert-alr-0002'):
        await user.should_see('Almacén')
        await user.should_see('14:25')
        await user.should_see('Movimiento en el almacén')
    user.find(marker='review-alr-0002').click()
    await user.should_see('Estado de la alerta actualizado.')
    await user.should_see('Atendida por Ana López' if role == 'admin' else 'Atendida por Carlos Ruiz')
    with user.scope(marker='alert-alr-0002'):
        await user.should_see('En revisión')
    user.find(marker='resolve-alr-0002').click()
    await user.should_not_see(marker='resolve-alr-0002')
    with user.scope(marker='alert-alr-0002'):
        await user.should_see('Resuelta')
    current = repositories.alerts.get('alr-0002')
    assert current is not None and current.status is AlertStatus.RESOLVED and current.handled_by
    for identifier in ('ventilador-tienda', 'led-aviso', 'alarma-digital'):
        before = repositories.actuators.get(identifier)
        assert before is not None
        user.find(marker=f'actuator-{identifier}').click()
        await user.should_see('Estado del equipo actualizado.')
        after = repositories.actuators.get(identifier)
        assert after is not None and after.is_on is not before.is_on and after.mode is ActuatorMode.MANUAL
    user.find(marker='automatic-ventilador-tienda').click()
    await user.should_see('Ventilador en modo automático.')
    await user.should_not_see(marker='automatic-ventilador-tienda')
    with user.scope(marker='equipment-ventilador-tienda'):
        await user.should_see('Modo automático')
        await user.should_see('Apagado')


async def test_manager_can_consult_equipment_but_sees_no_controls(user: User) -> None:
    await enter(user, 'gerente')
    await user.should_see('Estado de los equipos')
    await user.should_see('Ventilador de la tienda')
    await user.should_see('Zona: Almacén')  # el nombre de la zona, no su identificador
    await user.should_not_see('Zona: almacen')
    await user.should_not_see('Revisar alertas')
    for text in ('Control de equipos', 'Encender', 'Apagar', 'Volver a automático', 'En revisión', 'Marcar resuelta'):
        await user.should_not_see(text)
    await user.open('/supervision')
    await user.should_see('Dashboard · Gerente')
    await user.should_not_see('Control de equipos')


async def test_server_rules_timer_refreshes_dashboard_and_notifies_security(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    repositories = Repositories.from_json_dir(data_dir)
    repositories.actuators.modify(
        'ventilador-tienda',
        lambda item: replace(
            item,
            is_on=False,
            mode=ActuatorMode.AUTOMATIC,
        ),
    )
    with patch.object(app, 'timer', wraps=app.timer) as timers:
        async with user_simulation(main_file=MAIN_FILE) as user:
            await enter(user, 'seguridad')
            repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, value=30))
            await user.should_see('Nueva alerta: Temperatura crítica', retries=LOGIN_RETRIES)
            await user.should_see('2 alertas pendientes', retries=LOGIN_RETRIES)
            with user.scope(marker='equipment-ventilador-tienda'):
                await user.should_see('Encendido', retries=LOGIN_RETRIES)
            await user.open('/supervision')
            await user.should_see('Temperatura crítica', retries=LOGIN_RETRIES)
            rule_timers = [call for call in timers.call_args_list if call.args[1].__name__ == '_evaluate_rules']
            assert len(rule_timers) == 1


async def test_zero_interval_disables_server_rules_and_watcher(user: User, repositories: Repositories) -> None:
    with patch.object(app, 'timer', wraps=app.timer) as timers:
        await enter(user, 'seguridad')
        assert not [call for call in timers.call_args_list if call.args[1].__name__ == '_evaluate_rules']
        before = repositories.alerts.list_all()
        repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, value=30))
        await user.open('/supervision')
        assert repositories.alerts.list_all() == before


async def test_alert_watcher_stops_after_permission_is_revoked(
    user: User,
    repositories: Repositories,
    services: Services,
) -> None:
    await enter(user, 'seguridad')
    initial = services.supervision.open_alerts()
    watcher = AlertWatcher(services.supervision, initial, None, 0, allowed=lambda: False)
    repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, value=30))
    services.rules.evaluate()
    watcher.check()
    await user.should_not_see('Nueva alerta: Temperatura crítica')


async def test_configuration_action_revalidates_permissions(user: User, repositories: Repositories) -> None:
    await enter(user, 'admin')
    await user.open('/configuracion')
    original = repositories.config.load()
    user.find(marker='config-fan').clear().type('20')
    repositories.users.modify('usr-ana', lambda account: replace(account, role=Role.MANAGER))
    user.find('Guardar configuración').click()
    await user.should_see('Dashboard · Gerente')
    assert repositories.config.load() == original


async def test_configuration_live_data_refreshes_external_changes(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    """El formulario abierto refleja una configuración guardada desde otro cliente."""
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'admin')
        await user.open('/configuracion')
        repositories = Repositories.from_json_dir(data_dir)
        repositories.config.modify(lambda config: replace(config, facility_name='Establecimiento actualizado'))
        await user.should_see('Establecimiento actualizado', retries=LOGIN_RETRIES)
        field = next(iter(user.find(marker='config-fan').elements))
        assert isinstance(field, ui.number) and field.value == 26


async def test_configuration_poll_preserves_unsaved_numbers_and_switches(
    user: User, repositories: Repositories, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[ConfigurationPage] = []
    render = ConfigurationPage.render

    def capture(page: ConfigurationPage) -> None:
        render(page)
        pages.append(page)

    monkeypatch.setattr(ConfigurationPage, 'render', capture)
    await enter(user, 'admin')
    await user.open('/configuracion')
    user.find(marker='config-fan').clear().type('22')
    user.find(marker='zone-almacen').click()
    repositories.config.modify(lambda config: replace(config, facility_name='Nombre actualizado'))
    pages[-1]._config.poll()
    await asyncio.sleep(0.05)  # deja que NiceGUI ejecute la reconstrucción solicitada por el refresco
    field = next(iter(user.find(marker='config-fan').elements))
    switch = next(iter(user.find(marker='zone-almacen').elements))
    assert isinstance(field, ui.number) and field.value == 22
    assert isinstance(switch, ui.switch) and not switch.value
    user.find('Guardar configuración').click()
    await user.should_see('Configuración guardada.')
    await user.should_see('Nombre actualizado')
    assert repositories.config.load().fan_threshold == 22
    assert not next(zone for zone in repositories.config.load().zones if zone.id == 'almacen').restricted


@pytest.mark.parametrize('filename', ['alertas.json', 'configuracion.json'])
async def test_shell_recovers_from_initial_malformed_alert_data(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, filename: str,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    path = data_dir / filename
    original = path.read_bytes()
    path.write_text('{incompleto', encoding='utf-8')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.should_see('No se pudieron leer los datos')
        path.write_bytes(original)
        await user.should_see('1 alerta pendiente', retries=LOGIN_RETRIES)
        await user.should_not_see('Nueva alerta: Movimiento en zona restringida')


@pytest.mark.parametrize('action', ['guardar', 'automatico'])
async def test_rule_actions_run_outside_event_loop(
    user: User, monkeypatch: pytest.MonkeyPatch, action: str,
) -> None:
    await enter(user, 'admin')
    await user.open('/configuracion' if action == 'guardar' else '/supervision')
    loop_thread = get_ident()
    calls: list[int] = []

    def evaluate(controller: RulesController) -> RulesResult:
        calls.append(get_ident())
        assert get_ident() != loop_thread
        return RulesResult()

    monkeypatch.setattr(RulesController, 'evaluate', evaluate)
    if action == 'guardar':
        user.find('Guardar configuración').click()
        await user.should_see('Configuración guardada.')
    else:
        user.find(marker='automatic-ventilador-tienda').click()
        await user.should_see('Ventilador en modo automático.')
    assert len(calls) == 1


async def test_configuration_keeps_edits_made_while_save_is_running(
    user: User, monkeypatch: pytest.MonkeyPatch, repositories: Repositories,
) -> None:
    await enter(user, 'admin')
    await user.open('/configuracion')
    started, release = Event(), Event()

    def evaluate(controller: RulesController) -> RulesResult:
        started.set()
        assert release.wait(timeout=5)
        return RulesResult()

    monkeypatch.setattr(RulesController, 'evaluate', evaluate)
    user.find(marker='config-fan').clear().type('22')
    user.find('Guardar configuración').click()
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        user.find(marker='config-fan').clear().type('23')
    finally:
        release.set()
    await user.should_see('Configuración guardada.')
    field = next(iter(user.find(marker='config-fan').elements))
    assert isinstance(field, ui.number) and field.value == 23
    assert repositories.config.load().fan_threshold == 22


async def test_async_actions_survive_a_refresh_while_they_run(
    user: User, monkeypatch: pytest.MonkeyPatch, repositories: Repositories,
) -> None:
    """«Volver a automático» trabaja en un hilo; si mientras tanto un refresco vuelve a dibujar el bloque
    del botón (NiceGUI redibuja en segundo plano), el aviso y la relectura se hacen igualmente en la página."""
    await enter(user, 'seguridad')
    await user.open('/supervision')
    started, release = Event(), Event()
    original = RulesController.evaluate

    def evaluate(controller: RulesController) -> RulesResult:
        started.set()
        assert release.wait(timeout=5)
        return original(controller)

    monkeypatch.setattr(RulesController, 'evaluate', evaluate)
    user.find(marker='automatic-ventilador-tienda').click()
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        user.find(marker='actuator-led-aviso').click()  # vuelve a dibujar Supervisión: el botón pulsado desaparece
        await asyncio.sleep(0.1)
    finally:
        release.set()
    await user.should_see('Ventilador en modo automático.')
    with user.scope(marker='equipment-ventilador-tienda'):
        await user.should_see('Modo automático')
    fan = repositories.actuators.get('ventilador-tienda')
    assert fan is not None and fan.mode is ActuatorMode.AUTOMATIC
