"""Pantallas del análisis de imagen con YOLO, con la simulación de usuario de NiceGUI (sin ventana)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User, user_simulation
from test_supervision_ui import LOGIN_RETRIES, MAIN_FILE, enter
from test_vision import FakeDetector, FakeFrames, camera, camera_alerts, quiet_almacen

import lumina.app
from lumina.controllers import FixedClock, Services, VisionController
from lumina.models import AlertType
from lumina.repositories import Repositories
from lumina.views.components import Picture


def analyze(repositories: Repositories, clock: FixedClock, people: dict[str, int]) -> None:
    """Un ciclo de análisis con el detector de prueba, sobre los mismos datos que usa la aplicación."""
    VisionController(repositories, clock, FakeDetector(people), FakeFrames()).step()


def use_fake_vision(monkeypatch: pytest.MonkeyPatch, detector: FakeDetector) -> None:
    """La aplicación arranca con el detector y los fotogramas de prueba en lugar de YOLO y OpenCV."""
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    monkeypatch.setenv('LUMINA_VISION', 'true')
    monkeypatch.setattr(lumina.app, 'YoloPersonDetector', lambda *args, **kwargs: detector)
    monkeypatch.setattr(lumina.app, 'VideoFrameReader', lambda *args, **kwargs: FakeFrames())


async def test_a_person_in_a_restricted_zone_lights_the_camera_led_and_shows_the_image(
    user: User, repositories: Repositories, clock: FixedClock,
) -> None:
    analyze(repositories, clock, {'cam-almacen': 2, 'cam-parking': 1})
    await enter(user, 'seguridad')
    await user.open('/supervision')
    await user.should_see(marker='presence-cam-almacen')
    with user.scope(marker='camera-cam-almacen'):
        await user.should_see('PERSONA EN ZONA RESTRINGIDA')
        await user.should_see('YOLO: 2 personas en zona restringida · 14/10/2026 14:30')
    await user.should_not_see(marker='presence-cam-parking')  # el parking no es una zona restringida
    with user.scope(marker='camera-cam-parking'):
        await user.should_see('YOLO: 1 persona · 14/10/2026 14:30')
    await user.should_see('Análisis de imagen con YOLO desactivado.')  # los tests no lo arrancan
    user.find(marker='open-capture-cam-almacen').click()
    await user.should_see('Imagen analizada por YOLO')
    capture = camera(repositories, 'cam-almacen').capture
    assert capture is not None
    assert any(image.props.get('src') == f'/{capture}' for image in user.find(Picture).elements)
    user.find('Cerrar').click()
    await user.should_not_see('Imagen analizada por YOLO')


async def test_nobody_in_sight_keeps_the_led_off(user: User, repositories: Repositories, clock: FixedClock) -> None:
    analyze(repositories, clock, {})
    await enter(user, 'seguridad')
    await user.open('/supervision')
    with user.scope(marker='camera-cam-almacen'):
        await user.should_see('YOLO: nadie a la vista · 14/10/2026 14:30')
    await user.should_not_see(marker='presence-cam-almacen')
    await user.should_not_see(marker='open-capture-cam-almacen')


async def test_cameras_not_yet_analyzed_say_so(user: User) -> None:
    await enter(user, 'admin')
    await user.open('/supervision')
    with user.scope(marker='camera-cam-almacen'):
        await user.should_see('YOLO: sin analizar')
    await user.should_not_see(marker='presence-cam-almacen')


async def test_the_alert_shows_the_image_where_the_person_was_seen(
    user: User, repositories: Repositories, services: Services, clock: FixedClock,
) -> None:
    quiet_almacen(repositories)
    analyze(repositories, clock, {'cam-almacen': 1})
    services.rules.evaluate()
    [alert] = camera_alerts(repositories)
    await enter(user, 'seguridad')
    await user.should_see('1 alerta pendiente')
    await user.open('/supervision')
    with user.scope(marker=f'alert-{alert.id}'):
        await user.should_see('Persona en zona restringida')
        await user.should_see('Sensor: cam-almacen')
    image = user.find(marker=f'capture-{alert.id}').elements.pop()
    assert isinstance(image, Picture) and image.props['src'] == f'/{alert.capture}'
    response = await user.http_client.get(f'/{alert.capture}')  # la imagen se sirve a la página
    assert response.status_code == 200 and response.content[:2] == b'\xff\xd8'
    with user.scope(marker='equipment-led-aviso'):
        await user.should_see('Encendido')


async def test_the_live_analysis_turns_on_the_led_and_warns_security(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path,
) -> None:
    repositories = Repositories.from_json_dir(data_dir)
    quiet_almacen(repositories)
    use_fake_vision(monkeypatch, FakeDetector({'cam-almacen': 1}))
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.should_see('Nueva alerta: Persona en zona restringida · Almacén', retries=LOGIN_RETRIES)
        with user.scope(marker='equipment-led-aviso'):
            await user.should_see('Encendido', retries=LOGIN_RETRIES)
        await user.open('/supervision')
        await user.should_see('PERSONA EN ZONA RESTRINGIDA', retries=LOGIN_RETRIES)
        await user.should_see('Análisis de imagen con YOLO-prueba cada 0,1 s', retries=LOGIN_RETRIES)
    alerts = camera_alerts(repositories)
    assert len(alerts) == 1 and alerts[0].capture  # una sola alerta abierta aunque siga viéndola
    for identifier in ('led-aviso', 'alarma-digital'):
        actuator = repositories.actuators.get(identifier)
        assert actuator is not None and actuator.is_on


async def test_the_screen_explains_when_yolo_is_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    use_fake_vision(
        monkeypatch,
        FakeDetector(unavailable='falta el paquete ultralytics (pip install -r requirements.txt)'),
    )
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'admin')
        await user.open('/supervision')
        await user.should_see('Análisis de imagen no disponible: falta el paquete ultralytics', retries=LOGIN_RETRIES)


async def test_new_analyses_refresh_the_captions_without_restarting_the_videos(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.open('/supervision')
        videos = {element.id for element in user.find(ui.video).elements}
        assert len(videos) == 2
        Repositories.from_json_dir(data_dir).cameras.modify(
            'cam-almacen', lambda item: item.with_analysis(3, datetime(2026, 10, 14, 14, 31), None)
        )
        await user.should_see('YOLO: 3 personas en zona restringida', retries=LOGIN_RETRIES)
        await user.should_see(marker='presence-cam-almacen')
        assert {element.id for element in user.find(ui.video).elements} == videos  # siguen los mismos vídeos


async def test_the_manager_never_sees_cameras_nor_images(user: User, repositories: Repositories) -> None:
    repositories.cameras.modify('cam-almacen', lambda item: replace(item, people=2))
    await enter(user, 'gerente')
    await user.should_not_see('PERSONA EN ZONA RESTRINGIDA')
    await user.open('/supervision')
    await user.should_see('Dashboard · Gerente')
    assert not [alert for alert in repositories.alerts.list_all() if alert.type is AlertType.PERSON_IN_RESTRICTED_ZONE]
