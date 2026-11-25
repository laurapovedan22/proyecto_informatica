"""Aceptación de H2.1–H2.4 con usuarios simulados, sin abrir ventana ni navegador."""

from __future__ import annotations

import asyncio
import random
import re
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User, user_simulation

from lumina.controllers import FixedClock, SupervisionController, SystemClock
from lumina.models import Role, SensorStatus, SupervisionSnapshot
from lumina.repositories import Repositories
from lumina.views.components import Button, Text
from lumina.views.components.base import Picture
from lumina.views.components.camera import CameraTile
from lumina.views.components.data import ProgressMeter
from lumina.views.pages.base import LiveData
from lumina.views.pages.dashboard import DashboardPage
from lumina.views.pages.supervision import SupervisionPage
from lumina.views.routes import Route
from scripts.simular_sensores import SensorSimulator

MAIN_FILE = Path(__file__).resolve().parent.parent / 'main.py'
ASSETS_DIR = MAIN_FILE.parent / 'assets'
LOGIN_RETRIES = 40


async def enter(user: User, role: str) -> None:
    """Inicia sesión con una de las cuentas de demostración."""
    email, password = {
        'admin': ('ana.lopez@lumina.es', 'admin123'),
        'seguridad': ('carlos.ruiz@lumina.es', 'seguridad123'),
        'gerente': ('marta.garcia@lumina.es', 'gerente123'),
    }[role]
    await user.open('/login')
    user.find(marker='login-email').type(email)
    user.find(marker='login-password').type(password)
    user.find('Entrar').click()
    await user.should_see('Tu cuenta', retries=LOGIN_RETRIES)


@pytest.mark.parametrize('role', ['admin', 'seguridad', 'gerente'])
async def test_all_dashboards_show_occupancy_climate_units_and_reading_times(user: User, role: str) -> None:
    await enter(user, role)
    for text in (
        '23,6 °C',
        '48 %',
        '86 / 150 personas',
        '18 plazas libres',
        '32 de 50 ocupadas',
        'Última lectura:',
        '14:30',
        '64 personas hasta completar el aforo',
        'Tu cuenta',
        'Funciones de tu perfil',
        'Disponible en este panel',
    ):
        await user.should_see(text)
    assert DashboardPage.CURRENT_SPRINT == 3
    assert not any(
        button.props.get('href') == Route.DASHBOARD for button in user.find(Button).elements if button.text == 'Abrir'
    )
    meters = user.find(ProgressMeter).elements
    assert len(meters) == 2
    assert {(meter.props['aria-valuenow'], meter.props['aria-valuemax']) for meter in meters} == {
        ('86', '150'),
        ('32', '50'),
    }
    if role in ('admin', 'seguridad'):
        await user.should_see('Estado de los sensores')
        await user.should_see('9 sensores')
        await user.should_see('Supervisión')
    else:
        await user.should_not_see('Estado de los sensores')
        await user.should_not_see('Supervisión')
    if role == 'admin':
        await user.should_see('Solicitudes')
        await user.should_see('Desactivadas')


@pytest.mark.parametrize('role', ['admin', 'seguridad'])
async def test_security_and_admin_see_cameras_zones_and_sensor_values(user: User, role: str) -> None:
    await enter(user, role)
    await user.open('/supervision')
    for text in (
        'Cámaras, detecciones por zona y estado de los sensores',
        'Cámara 1 · Almacén',
        'Cámara 2 · Parking',
        'EN DIRECTO',
        'Almacén · Movimiento detectado',
        '14:25',
        'Detección de movimiento por zona',
        'Salida de emergencia',
        'Sin movimiento',
        'Sensores',
        '23,6 °C',
        '48 %',
        'Presencia',
        'Activo',
        'Última actualización',
    ):
        await user.should_see(text)
    await user.should_see('Control de equipos')
    await user.should_not_see('Marcar revisada')
    await user.should_see('Alertas')
    assert user.find(marker='camera-cam-almacen').elements
    assert user.find(marker='camera-cam-parking').elements
    assert user.find(marker='video-cam-almacen').elements  # vídeo real, no una vista simulada
    assert user.find(marker='video-cam-parking').elements
    await user.should_not_see('Vista simulada · Sin vídeo real')
    with user.scope(marker='motion-almacen'):
        await user.should_see('Movimiento detectado')
    with user.scope(marker='motion-salida-emergencia'):
        await user.should_see('Sin movimiento')


async def test_manager_cannot_see_cameras_even_by_direct_route(user: User) -> None:
    await enter(user, 'gerente')
    await user.open('/supervision')
    await user.should_see('Dashboard · Gerente')
    await user.should_not_see('Cámara 1 · Almacén')
    await user.should_not_see('Cámara 2 · Parking')
    await user.should_not_see('Detección de movimiento por zona')


async def test_supervision_shows_missing_failed_and_stale_readings(
    user: User,
    repositories: Repositories,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SystemClock, 'now', lambda self: datetime(2026, 10, 14, 14, 30))
    repositories.config.save(replace(repositories.config.load(), max_reading_age_minutes=10))
    repositories.sensors.modify('temp-tienda', lambda sensor: replace(sensor, value=None))
    repositories.sensors.modify('hum-tienda', lambda sensor: replace(sensor, status=SensorStatus.ERROR))
    repositories.sensors.modify('temp-almacen', lambda sensor: replace(sensor, updated_at=datetime(2026, 10, 14, 14)))
    await enter(user, 'seguridad')
    await user.open('/supervision')
    for sensor_id, state, value in [
        ('temp-tienda', 'Sin datos', 'Sin datos'),
        ('hum-tienda', 'Error', '48 %'),
        ('temp-almacen', 'Desactualizado', '19,8 °C'),
    ]:
        with user.scope(marker=f'sensor-{sensor_id}'):
            await user.should_see(state)
            await user.should_see(value)
            await user.should_see('%' if sensor_id == 'hum-tienda' else '°C')


async def test_camera_url_is_rendered_and_offline_camera_keeps_zone_detection(
    user: User,
    repositories: Repositories,
) -> None:
    repositories.cameras.modify('cam-almacen', lambda camera: replace(camera, stream_url='/assets/logo-icono.png'))
    repositories.cameras.modify('cam-parking', lambda camera: replace(camera, status=SensorStatus.ERROR))
    await enter(user, 'seguridad')
    await user.open('/supervision')
    images = user.find(Picture).elements
    assert any(
        image.props.get('src') == '/assets/logo-icono.png' and image.props.get('alt') == 'Cámara 1 · Almacén'
        for image in images
    )
    with user.scope(marker='camera-cam-parking'):
        await user.should_see('Cámara sin conexión')
        await user.should_see('Parking · Sin datos')


async def test_cameras_play_a_supermarket_surveillance_video(user: User, repositories: Repositories) -> None:
    """Cada cámara reproduce en bucle, sin sonido ni controles, una grabación real de videovigilancia.

    Los datos de ejemplo usan copias locales, servidas por la aplicación en ``/assets/camaras``, de dos
    vídeos de dominio público de Wikimedia Commons: se ven sin conexión y YOLO analiza el mismo fichero.
    """
    await enter(user, 'seguridad')
    await user.open('/supervision')
    for camera in repositories.cameras.list_all():
        assert camera.stream_url is not None and camera.stream_url.startswith('/assets/camaras/')
        assert (ASSETS_DIR / camera.stream_url.removeprefix('/assets/')).is_file()
        assert CameraTile.is_video(camera.stream_url)
        video = user.find(marker=f'video-{camera.id}').elements.pop()
        assert isinstance(video, ui.video)
        assert video.props['src'] == camera.stream_url
        assert all(video.props[flag] for flag in ('autoplay', 'muted', 'loop', 'playsinline'))
        assert 'controls' not in video.props
        clock = user.find(marker=f'clock-{camera.id}').elements.pop()
        assert isinstance(clock, Text) and re.fullmatch(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', clock.text)
    with user.scope(marker='camera-cam-almacen'):
        await user.should_see('EN DIRECTO')
        await user.should_see('· Cámara 1 · Almacén')
        await user.should_not_see('Sin señal de vídeo')
    response = await user.http_client.get('/assets/camaras/tienda.webm')
    assert response.status_code == 200 and response.content[:4] == b'\x1a\x45\xdf\xa3'  # cabecera WebM


def test_video_urls_are_recognised_by_their_extension() -> None:
    assert CameraTile.is_video('https://ejemplo.es/camaras/tienda.webm')
    assert CameraTile.is_video('https://ejemplo.es/parking.MP4?calidad=480p')
    assert not CameraTile.is_video('http://192.168.1.20/mjpeg/stream')
    assert not CameraTile.is_video('/assets/logo-icono.png')


async def test_a_camera_without_url_keeps_the_simulated_view(user: User, repositories: Repositories) -> None:
    repositories.cameras.modify('cam-parking', lambda camera: replace(camera, stream_url=None))
    await enter(user, 'seguridad')
    await user.open('/supervision')
    with user.scope(marker='camera-cam-parking'):
        await user.should_see('Vista simulada · Sin vídeo real')
        await user.should_not_see('EN DIRECTO')
    await user.should_see(marker='video-cam-almacen')
    await user.should_not_see(marker='video-cam-parking')


async def test_a_camera_that_loses_its_signal_says_so(user: User) -> None:
    await enter(user, 'seguridad')
    await user.open('/supervision')
    await user.should_not_see('Sin señal de vídeo')
    user.find(marker='video-cam-parking').trigger('error')  # el navegador no puede reproducir el vídeo
    with user.scope(marker='camera-cam-parking'):
        await user.should_see('Sin señal de vídeo')
        await user.should_see('SIN SEÑAL')
        await user.should_see('Parking · Sin datos')  # la detección de la zona se sigue mostrando
    with user.scope(marker='camera-cam-almacen'):
        await user.should_see('EN DIRECTO')
        await user.should_not_see('Sin señal de vídeo')


async def test_refreshes_update_camera_captions_without_restarting_the_video(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.open('/supervision')
        await user.should_see('Almacén · Movimiento detectado')
        videos = {element.id for element in user.find(ui.video).elements}
        assert len(videos) == 2
        Repositories.from_json_dir(data_dir).sensors.modify(
            'mov-almacen', lambda sensor: replace(sensor, value=0, updated_at=datetime(2026, 10, 14, 14, 31)),
        )
        await user.should_see('Almacén · Sin movimiento', retries=LOGIN_RETRIES)
        with user.scope(marker='motion-almacen'):
            await user.should_see('Sin movimiento')
        assert {element.id for element in user.find(ui.video).elements} == videos  # siguen los mismos vídeos


async def test_the_camera_clock_ticks_every_second(monkeypatch: pytest.MonkeyPatch, clock: FixedClock) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    monkeypatch.setattr(SystemClock, 'now', lambda self: clock.now())
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.open('/supervision')
        await user.should_see('14/10/2026 14:30:00')
        clock.advance(timedelta(seconds=7))
        await user.should_see('14/10/2026 14:30:07', retries=LOGIN_RETRIES)


async def test_the_live_simulation_refreshes_the_screens_by_itself(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path,
) -> None:
    """Sin simulador externo, la propia aplicación genera lecturas nuevas: los datos nunca se quedan fijos."""
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    monkeypatch.setenv('LUMINA_SIMULATION', 'true')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'gerente')
        await user.should_see('Última lectura: Hoy ·', retries=LOGIN_RETRIES)  # las de ejemplo son del 14/10/2026
        repositories = Repositories.from_json_dir(data_dir)
        for _ in range(LOGIN_RETRIES):  # cada ciclo actualiza los sensores uno a uno
            if all(item.updated_at is not None and item.updated_at.date() == date.today()
                   for item in repositories.sensors.list_all()):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail('La simulación en vivo no ha renovado todas las lecturas.')
        await user.should_not_see('14/10/2026 14:30', retries=LOGIN_RETRIES)


@pytest.mark.parametrize('route', ['/dashboard', '/supervision'])
async def test_new_json_readings_refresh_the_open_screen(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    route: str,
) -> None:
    """Cambia sensores.json a través de los repositorios y espera al temporizador real de LiveData."""
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.open(route)
        await user.should_see('23,6 °C')
        repositories = Repositories.from_json_dir(data_dir)
        repositories.sensors.modify(
            'temp-tienda',
            lambda sensor: replace(
                sensor,
                value=25.7,
                updated_at=datetime(2026, 10, 14, 14, 31),
            ),
        )
        repositories.sensors.modify(
            'hum-tienda',
            lambda sensor: replace(
                sensor,
                value=51.2,
                updated_at=datetime(2026, 10, 14, 14, 31),
            ),
        )
        repositories.sensors.modify(
            'mov-almacen',
            lambda sensor: replace(
                sensor,
                value=0,
                updated_at=datetime(2026, 10, 14, 14, 31),
            ),
        )
        await user.should_see('25,7 °C', retries=LOGIN_RETRIES)
        await user.should_see('51,2 %', retries=LOGIN_RETRIES)
        await user.should_see('14:31')
        await user.should_not_see('23,6 °C')
        if route == '/supervision':
            await user.should_see('Almacén · Sin movimiento', retries=LOGIN_RETRIES)


async def test_simulator_updates_dashboard_without_reload(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'gerente')
        simulator = SensorSimulator(
            Repositories.from_json_dir(data_dir), FixedClock(datetime(2026, 10, 14, 14, 32)), random.Random(7)
        )
        readings = simulator.step()
        temperature = next(sensor.value for sensor in readings if sensor.id == 'temp-tienda')
        assert temperature == 23.5
        await user.should_see('23,5 °C', retries=LOGIN_RETRIES)
        await user.should_see('14:32')


@pytest.mark.parametrize('route', ['/dashboard', '/supervision'])
async def test_initial_malformed_json_recovers_without_reload(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, route: str,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    path = data_dir / 'sensores.json'
    original = path.read_text(encoding='utf-8')
    path.write_text('{"sensores": [', encoding='utf-8')
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'admin')
        if route == '/dashboard':
            await user.should_see('Tu cuenta')
            await user.should_see('Funciones de tu perfil')
            await user.should_see('Solicitudes')
        else:
            await user.open(route)
        await user.should_see('No se pudieron leer los datos')
        await user.should_not_see('23,6 °C')
        path.write_text(original, encoding='utf-8')
        await user.should_see('23,6 °C', retries=LOGIN_RETRIES)
        if route == '/supervision':
            await user.should_see('Cámara 1 · Almacén')
            with user.scope(marker='sensor-temp-tienda'):
                await user.should_see('Activo')
        else:
            await user.should_see('86 / 150 personas')


@pytest.mark.parametrize('route', ['/dashboard', '/supervision'])
async def test_relative_dates_refresh_at_midnight_without_json_changes(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, clock: FixedClock, route: str,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    monkeypatch.setattr(SystemClock, 'now', lambda self: clock.now())
    path = data_dir / 'sensores.json'
    original = path.read_bytes()
    clock.advance(timedelta(hours=9, minutes=29))
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.open(route)
        await user.should_see('Hoy · 14:30')
        if route == '/dashboard':
            await user.should_see('Hoy · 23:59')
        clock.advance(timedelta(minutes=2))
        await user.should_see('14/10/2026 14:30', retries=LOGIN_RETRIES)
        await user.should_not_see('Hoy · 14:30')
        if route == '/dashboard':
            await user.should_see('14/10/2026 23:59', retries=LOGIN_RETRIES)
            await user.should_not_see('Hoy · 23:59')
        assert path.read_bytes() == original


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
async def test_nonfinite_readings_never_break_dashboard_or_supervision(
    user: User, repositories: Repositories, value: float,
) -> None:
    for sensor in repositories.sensors.list_all():
        repositories.sensors.modify(sensor.id, lambda current: replace(current, value=value))
    await enter(user, 'seguridad')
    await user.should_see('0 / 150 personas')
    await user.should_see('Sin datos · °C')
    await user.should_see('9 sensores')
    await user.open('/supervision')
    await user.should_see('Cámara 1 · Almacén')
    for sensor_id in ('temp-tienda', 'hum-tienda', 'aforo-tienda', 'vehiculos-parking', 'mov-almacen'):
        with user.scope(marker=f'sensor-{sensor_id}'):
            await user.should_see('Error')
            await user.should_see('Lectura inválida')
            await user.should_not_see('Activo')
    with user.scope(marker='motion-almacen'):
        await user.should_see('Error')
        await user.should_not_see('Sin movimiento')


@pytest.mark.parametrize('change', ['degradar', 'desactivar'])
async def test_open_supervision_revalidates_session_and_permission(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    change: str,
) -> None:
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0.1')
    calls = 0
    live_data: list[LiveData[SupervisionSnapshot]] = []
    snapshot = SupervisionController.snapshot
    render = SupervisionPage.render

    def count_snapshot(self: SupervisionController) -> SupervisionSnapshot:
        nonlocal calls
        calls += 1
        return snapshot(self)

    def capture_live_data(self: SupervisionPage) -> None:
        render(self)
        live_data.append(self._snapshot)

    monkeypatch.setattr(SupervisionController, 'snapshot', count_snapshot)
    monkeypatch.setattr(SupervisionPage, 'render', capture_live_data)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await enter(user, 'seguridad')
        await user.open('/supervision')
        await user.should_see('Cámara 1 · Almacén')
        repositories = Repositories.from_json_dir(data_dir)
        timer = live_data[-1]._timer
        assert timer is not None and timer.active
        assert calls > 0
        before = calls
        if change == 'degradar':
            repositories.users.modify('usr-carlos', lambda account: replace(account, role=Role.MANAGER))
            await user.should_see('Dashboard · Gerente', retries=LOGIN_RETRIES)
        else:
            repositories.users.modify('usr-carlos', lambda account: replace(account, active=False))
            await user.should_see('Iniciar sesión', retries=LOGIN_RETRIES)
        await user.should_not_see('Cámara 1 · Almacén')
        assert calls == before  # también impide consultar antes de comprobar el permiso
        assert not timer.active
        await asyncio.sleep(0.3)
        assert calls == before
        assert not timer.active
