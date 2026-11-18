"""Análisis de imagen con YOLO (ampliación del 18/11/2026): personas en zonas restringidas.

YOLO funciona como un sensor de movimiento de la zona de cada cámara: si ve a alguien en una zona
restringida, las reglas encienden el LED y la alarma y abren una alerta con la imagen marcada.
Casi todos los tests usan un detector y unos fotogramas de prueba; los que necesitan YOLO u
OpenCV de verdad se saltan si no están instalados.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator
from PIL import Image
from test_sprint3 import changes

from lumina.controllers import (
    CapturePainter,
    FixedClock,
    FrameReader,
    NotFoundError,
    PersonBox,
    PersonDetector,
    Services,
    VisionController,
    VisionUnavailableError,
)
from lumina.controllers.yolo import VideoFrameReader, YoloPersonDetector
from lumina.models import (
    ActuatorMode,
    AlertStatus,
    AlertType,
    Camera,
    SensorStatus,
    User,
    VisionState,
    Zone,
)
from lumina.repositories import Repositories
from lumina.settings import AppSettings

ROOT = Path(__file__).resolve().parent.parent


def frame(camera_id: str, size: tuple[int, int] = (320, 180)) -> Image.Image:
    """Fotograma gris que recuerda de qué cámara viene (para el detector de prueba)."""
    image = Image.new('RGB', size, (90, 90, 90))
    image.info['camera'] = camera_id
    return image


class FakeFrames(FrameReader):
    """Fotogramas de prueba; las cámaras de ``missing`` no tienen imagen."""

    def __init__(self, missing: frozenset[str] = frozenset()) -> None:
        self.missing = set(missing)
        self.calls: list[str] = []

    def read(self, camera: Camera, now: datetime) -> Image.Image | None:
        self.calls.append(camera.id)
        return None if camera.id in self.missing else frame(camera.id)


class FakeDetector(PersonDetector):
    """Ve en cada cámara las personas indicadas, o no puede cargarse si ``unavailable``."""

    def __init__(self, people: dict[str, int] | None = None, *, unavailable: str | None = None) -> None:
        self.people = dict(people or {})
        self.unavailable = unavailable
        self.prepared = 0

    @property
    def name(self) -> str:
        return 'YOLO-prueba'

    def prepare(self) -> None:
        self.prepared += 1
        if self.unavailable:
            raise VisionUnavailableError(self.unavailable)

    def detect(self, image: Image.Image) -> tuple[PersonBox, ...]:
        count = self.people.get(str(image.info.get('camera')), 0)
        return tuple(PersonBox(0.1 + 0.2 * index, 0.2, 0.25 + 0.2 * index, 0.9, 0.9) for index in range(count))


def vision(
    repositories: Repositories, clock: FixedClock, detector: FakeDetector, frames: FakeFrames | None = None,
) -> VisionController:
    return VisionController(repositories, clock, detector, frames or FakeFrames())


def quiet_almacen(repositories: Repositories) -> None:
    """Almacén sin movimiento, sin alertas abiertas y con el LED y la alarma apagados."""
    repositories.sensors.modify('mov-almacen', lambda sensor: replace(sensor, value=0))
    repositories.alerts.modify('alr-0002', lambda alert: replace(alert, status=AlertStatus.RESOLVED))
    for identifier in ('led-aviso', 'alarma-digital'):
        repositories.actuators.modify(identifier, lambda actuator: replace(actuator, is_on=False))


def camera(repositories: Repositories, camera_id: str) -> Camera:
    found = repositories.cameras.get(camera_id)
    assert found is not None
    return found


def camera_alerts(repositories: Repositories) -> list[Any]:
    return [alert for alert in repositories.alerts.list_all() if alert.type is AlertType.PERSON_IN_RESTRICTED_ZONE]


def rgb(image: Image.Image, point: tuple[int, int]) -> tuple[int, int, int]:
    pixel = image.convert('RGB').getpixel(point)
    assert isinstance(pixel, tuple)
    return int(pixel[0]), int(pixel[1]), int(pixel[2])


def schema_errors(name: str, data_dir: Path) -> list[str]:
    schema = json.loads((ROOT / 'schemas' / name.replace('.json', '.schema.json')).read_text(encoding='utf-8'))
    document = json.loads((data_dir / name).read_text(encoding='utf-8'))
    return [error.message for error in Draft202012Validator(schema).iter_errors(document)]


# --- Análisis de las cámaras ----------------------------------------------------------------------


def test_each_cycle_counts_people_and_keeps_the_marked_image(repositories: Repositories, clock: FixedClock) -> None:
    saved = vision(repositories, clock, FakeDetector({'cam-almacen': 2})).step()
    assert [item.id for item in saved] == ['cam-almacen', 'cam-parking']
    almacen, parking = camera(repositories, 'cam-almacen'), camera(repositories, 'cam-parking')
    assert (almacen.people, almacen.analyzed_at) == (2, clock.now())
    assert almacen.capture is not None and almacen.capture.startswith('capturas/cam-almacen-20261014-143000-')
    path = repositories.captures.path(almacen.capture)
    assert path is not None and path.read_bytes()[:2] == b'\xff\xd8'  # JPEG
    assert (parking.people, parking.capture) == (0, None)  # sin personas no se guarda imagen


def test_a_person_in_a_restricted_zone_lights_the_led_and_opens_an_alert_with_the_image(
    services: Services, repositories: Repositories, clock: FixedClock,
) -> None:
    quiet_almacen(repositories)
    vision(repositories, clock, FakeDetector({'cam-almacen': 1})).step()
    result = services.rules.evaluate()
    [alert] = result.alerts_created
    assert alert.type is AlertType.PERSON_IN_RESTRICTED_ZONE
    assert (alert.zone_id, alert.sensor_id) == ('almacen', 'cam-almacen')
    assert alert.capture == camera(repositories, 'cam-almacen').capture
    assert alert.created_at == clock.now()
    assert alert.description == 'Persona en zona restringida: Cámara 1 · Almacén (1 persona detectada por YOLO)'
    for identifier in ('led-aviso', 'alarma-digital'):
        actuator = repositories.actuators.get(identifier)
        assert actuator is not None and actuator.is_on and actuator.mode is ActuatorMode.AUTOMATIC
    assert {item.id for item in result.actuators_changed} == {'led-aviso', 'alarma-digital'}


def test_people_outside_restricted_zones_are_only_counted(
    services: Services, repositories: Repositories, clock: FixedClock,
) -> None:
    quiet_almacen(repositories)
    before = repositories.actuators.list_all()
    vision(repositories, clock, FakeDetector({'cam-parking': 3})).step()
    assert camera(repositories, 'cam-parking').people == 3
    assert services.rules.evaluate().alerts_created == ()
    assert repositories.actuators.list_all() == before


def test_restricting_a_zone_applies_to_people_already_seen(
    services: Services, repositories: Repositories, clock: FixedClock, admin: User,
) -> None:
    vision(repositories, clock, FakeDetector({'cam-parking': 2})).step()
    assert camera_alerts(repositories) == []
    current = changes(services)
    restricted = current.restricted_zone_ids | {'parking'}
    services.configuration.update(replace(current, restricted_zone_ids=restricted), admin)
    [alert] = camera_alerts(repositories)
    assert (alert.zone_id, alert.sensor_id) == ('parking', 'cam-parking')


def test_a_camera_alert_is_not_repeated_while_open(
    services: Services, repositories: Repositories, clock: FixedClock, security: User,
) -> None:
    quiet_almacen(repositories)
    controller = vision(repositories, clock, FakeDetector({'cam-almacen': 1}))
    controller.step()
    services.rules.evaluate()
    for _ in range(3):
        clock.advance(timedelta(seconds=5))
        controller.step()
        assert services.rules.evaluate().alerts_created == ()
    [first] = camera_alerts(repositories)
    services.supervision.update_alert(first.id, AlertStatus.RESOLVED, security)
    clock.advance(timedelta(seconds=5))
    controller.step()
    [second] = services.rules.evaluate().alerts_created  # sigue habiendo alguien: incidencia nueva
    assert second.id != first.id and second.type is AlertType.PERSON_IN_RESTRICTED_ZONE


def test_old_or_disconnected_camera_analyses_do_not_count(
    services: Services, repositories: Repositories, clock: FixedClock,
) -> None:
    quiet_almacen(repositories)
    repositories.config.modify(lambda config: replace(config, max_reading_age_minutes=10))
    repositories.cameras.modify(
        'cam-almacen', lambda item: item.with_analysis(2, clock.now() - timedelta(minutes=11), None)
    )
    assert services.rules.evaluate().alerts_created == ()
    repositories.cameras.modify('cam-almacen', lambda item: replace(item, analyzed_at=clock.now()))
    repositories.cameras.modify('cam-almacen', lambda item: replace(item, status=SensorStatus.ERROR))
    assert services.rules.evaluate().alerts_created == ()
    repositories.cameras.modify('cam-almacen', lambda item: replace(item, status=SensorStatus.ACTIVE))
    assert [alert.type for alert in services.rules.evaluate().alerts_created] == [AlertType.PERSON_IN_RESTRICTED_ZONE]


def test_without_an_image_nobody_is_assumed(services: Services, repositories: Repositories, clock: FixedClock) -> None:
    quiet_almacen(repositories)
    repositories.cameras.modify('cam-almacen', lambda item: item.with_analysis(2, clock.now(), None))
    vision(repositories, clock, FakeDetector({'cam-almacen': 2}), FakeFrames(frozenset({'cam-almacen'}))).step()
    assert camera(repositories, 'cam-almacen').analysis == (None, clock.now(), None)
    assert services.rules.evaluate().alerts_created == ()


def test_inactive_cameras_or_without_signal_are_not_analyzed(repositories: Repositories, clock: FixedClock) -> None:
    repositories.cameras.modify('cam-almacen', lambda item: replace(item, status=SensorStatus.ERROR))
    repositories.cameras.modify('cam-parking', lambda item: replace(item, stream_url=None))
    frames = FakeFrames()
    assert vision(repositories, clock, FakeDetector({'cam-almacen': 1}), frames).step() == []
    assert frames.calls == []


def test_the_status_says_which_model_is_working_or_why_not(repositories: Repositories, clock: FixedClock) -> None:
    detector = FakeDetector({'cam-almacen': 1}, unavailable='falta el paquete ultralytics')
    controller = vision(repositories, clock, detector)
    states = [controller.status.state]
    before = repositories.cameras.list_all()
    assert controller.step() == []
    states.append(controller.status.state)
    assert states == [VisionState.STARTING, VisionState.UNAVAILABLE]
    assert controller.status.detail == 'falta el paquete ultralytics'
    assert repositories.cameras.list_all() == before
    clock.advance(timedelta(seconds=30))
    controller.step()
    assert detector.prepared == 1  # no se reintenta en cada ciclo
    detector.unavailable = None
    clock.advance(VisionController.RETRY_AFTER)
    assert len(controller.step()) == 2
    assert (controller.status.state, controller.status.detail) == (VisionState.READY, 'YOLO-prueba')


def test_an_analysis_written_by_another_source_keeps_priority_for_two_minutes(
    repositories: Repositories, clock: FixedClock,
) -> None:
    controller = vision(repositories, clock, FakeDetector())
    controller.step()
    repositories.cameras.modify('cam-almacen', lambda item: item.with_analysis(5, clock.now(), None))  # otro programa
    clock.advance(timedelta(seconds=5))
    assert [item.id for item in controller.step()] == ['cam-parking']
    assert camera(repositories, 'cam-almacen').people == 5
    clock.advance(VisionController.EXTERNAL_HOLD)
    controller.step()
    assert camera(repositories, 'cam-almacen').people == 0


def test_an_image_can_be_analyzed_for_a_camera(repositories: Repositories, clock: FixedClock) -> None:
    controller = vision(repositories, clock, FakeDetector({'cam-parking': 4}))
    analyzed = controller.analyze('cam-parking', frame('cam-parking'))
    assert (analyzed.people, analyzed.analyzed_at) == (4, clock.now()) and analyzed.capture
    with pytest.raises(NotFoundError):
        controller.analyze('cam-inexistente', frame('cam-inexistente'))


# --- Capturas ---------------------------------------------------------------------------------------


def test_old_unused_captures_are_deleted_but_alert_images_stay(
    services: Services, repositories: Repositories, clock: FixedClock,
) -> None:
    quiet_almacen(repositories)
    detector = FakeDetector({'cam-almacen': 1})
    controller = vision(repositories, clock, detector)
    controller.step()
    services.rules.evaluate()
    [alert] = camera_alerts(repositories)
    clock.advance(timedelta(seconds=10))
    controller.step()
    latest = camera(repositories, 'cam-almacen').capture
    assert alert.capture and latest and latest != alert.capture
    latest_path = repositories.captures.path(latest)
    assert latest_path is not None
    folder = latest_path.parent
    (folder / 'notas.txt').write_text('no es una captura', encoding='utf-8')
    detector.people = {}
    clock.advance(timedelta(minutes=3))
    controller.step()
    assert sorted(path.name for path in folder.iterdir()) == sorted([alert.capture.split('/')[1], 'notas.txt'])


def test_capture_references_never_leave_their_folder(repositories: Repositories, data_dir: Path) -> None:
    captures = repositories.captures
    reference = captures.save('cam/almacén', datetime(2026, 10, 14, 14, 30), b'\xff\xd8imagen')
    assert reference.startswith('capturas/cam-almac-n-20261014-143000-')
    assert captures.path(reference) == data_dir / reference
    invalid_references = (
        '../usuarios.json', 'capturas/../usuarios.json', 'otra/cam-20261014-143000-abcdef.jpg', 'capturas/'
    )
    for invalid in invalid_references:
        assert captures.path(invalid) is None


def test_the_painter_marks_people_in_red_only_in_restricted_zones() -> None:
    camera = Camera('cam-almacen', 'Cámara 1 · Almacén', 'almacen')
    person = PersonBox(0.25, 0.25, 0.75, 0.9, 0.87)
    moment = datetime(2026, 10, 14, 14, 30)
    colors: dict[bool, tuple[int, int, int]] = {}
    for restricted in (True, False):
        zone = Zone('almacen', 'Almacén', restricted)
        data = CapturePainter.paint(frame('cam', (960, 540)), [person], camera, zone, moment)
        with Image.open(BytesIO(data)) as picture:
            assert picture.format == 'JPEG' and picture.size == (960, 540)
            colors[restricted] = rgb(picture, (241, 360))  # borde izquierdo del recuadro de la persona
            assert rgb(picture, (480, 300))[0] < 120  # el interior del recuadro no se pinta
    red, green, _ = colors[True]
    assert red > green + 80
    red, green, _ = colors[False]
    assert green > red


def test_large_frames_are_reduced_before_saving() -> None:
    data = CapturePainter.paint(
        frame('cam', (1920, 1080)), [], Camera('c', 'C', 'z'), Zone('z', 'Z'), datetime(2026, 10, 14, 14, 30)
    )
    with Image.open(BytesIO(data)) as picture:
        assert picture.size == (CapturePainter.MAX_WIDTH, 540)


# --- Contrato JSON ------------------------------------------------------------------------------------


def test_camera_analysis_and_alert_images_round_trip_through_json(repositories: Repositories, data_dir: Path) -> None:
    analyzed = camera(repositories, 'cam-almacen').with_analysis(
        3, datetime(2026, 10, 14, 14, 30, 5), 'capturas/cam-almacen-20261014-143005-abcdef.jpg'
    )
    repositories.cameras.update(analyzed)
    alert = repositories.alerts.get('alr-0002')
    assert alert is not None
    repositories.alerts.update(replace(alert, capture=analyzed.capture))
    fresh = Repositories.from_json_dir(data_dir)  # sin caché: se vuelve a leer el JSON
    assert camera(fresh, 'cam-almacen') == analyzed
    reloaded = fresh.alerts.get('alr-0002')
    assert reloaded is not None and reloaded.capture == analyzed.capture
    stored = json.loads((data_dir / 'sensores.json').read_text(encoding='utf-8'))['camaras'][0]
    assert (stored['personas'], stored['analizada_en']) == (3, '2026-10-14T14:30:05')


def test_what_the_analysis_writes_follows_the_schemas(
    services: Services, repositories: Repositories, clock: FixedClock, data_dir: Path,
) -> None:
    quiet_almacen(repositories)
    vision(repositories, clock, FakeDetector({'cam-almacen': 2, 'cam-parking': 1}), FakeFrames()).step()
    services.rules.evaluate()
    vision(repositories, clock, FakeDetector(), FakeFrames(frozenset({'cam-parking'}))).step()
    assert camera_alerts(repositories)
    assert schema_errors('sensores.json', data_dir) == []
    assert schema_errors('alertas.json', data_dir) == []


# --- Piezas reales: YOLO y OpenCV -----------------------------------------------------------------------


def test_importing_lumina_does_not_load_yolo_or_opencv() -> None:
    code = (
        'import sys, lumina.app, lumina.controllers.yolo; '
        'print(sorted(name for name in ("ultralytics", "torch", "cv2") if name in sys.modules))'
    )
    output = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert output.stdout.strip() == '[]'


def test_without_ultralytics_the_analysis_is_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable in YoloPersonDetector.ENVIRONMENT:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setitem(sys.modules, 'ultralytics', None)  # como si no estuviera instalado
    detector = YoloPersonDetector('yolo26n.pt', tmp_path)
    with pytest.raises(VisionUnavailableError, match='falta el paquete ultralytics'):
        detector.prepare()
    assert os.environ['YOLO_OFFLINE'] == '1'  # sin telemetría ni comprobaciones de versión


@pytest.mark.parametrize(('model', 'name'), [('yolo26n.pt', 'YOLO26n'), ('/modelos/yolo11s.pt', 'YOLO11s'),
                                             ('personas.pt', 'personas')])
def test_the_detector_shows_the_model_name(model: str, name: str) -> None:
    assert YoloPersonDetector(model).name == name


def test_the_frame_reader_reads_local_images(tmp_path: Path) -> None:
    path = tmp_path / 'camara.png'
    Image.new('RGB', (64, 48), (10, 200, 30)).save(path)
    reader = VideoFrameReader(tmp_path / 'videos')
    image = reader.read(Camera('c', 'C', 'z', stream_url=str(path)), datetime(2026, 10, 14, 14, 30))
    assert image is not None and image.size == (64, 48) and image.mode == 'RGB'
    assert reader.read(Camera('c', 'C', 'z', stream_url=path.as_uri()), datetime(2026, 10, 14, 14, 30)) is not None
    for url in (str(tmp_path / 'no-existe.jpg'), 'ftp://ejemplo.es/camara.jpg'):
        assert reader.read(Camera('c', 'C', 'z', stream_url=url), datetime(2026, 10, 14, 14, 30)) is None


def test_internet_videos_are_downloaded_once_with_lumina_user_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b'video-de-prueba')

    frames: list[Path] = []

    def video_frame(path: Path, now: datetime) -> Image.Image:
        frames.append(path)
        return frame('cam')

    monkeypatch.setattr(VideoFrameReader, '_video_frame', staticmethod(video_frame))
    reader = VideoFrameReader(tmp_path / 'videos', transport=httpx.MockTransport(server))
    camera = Camera('cam', 'Cámara', 'almacen', stream_url='https://ejemplo.es/camaras/tienda.webm')
    assert reader.read(camera, datetime(2026, 10, 14, 14, 30)) is None  # se está descargando
    reader.wait_for_downloads(timeout=5)
    for _ in range(2):
        assert reader.read(camera, datetime(2026, 10, 14, 14, 30)) is not None
    assert len(requests) == 1 and requests[0].headers['User-Agent'] == VideoFrameReader.USER_AGENT
    assert len(frames) == 2 and frames[0].parent == tmp_path / 'videos' and frames[0].suffix == '.webm'
    assert frames[0].read_bytes() == b'video-de-prueba'


def test_the_frame_reader_uses_the_videos_served_by_the_application(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    frames: list[Path] = []

    def video_frame(path: Path, now: datetime) -> Image.Image:
        frames.append(path)
        return frame('cam')

    monkeypatch.setattr(VideoFrameReader, '_video_frame', staticmethod(video_frame))
    reader = VideoFrameReader(tmp_path / 'videos', local_urls={'/assets': ROOT / 'assets'})
    moment = datetime(2026, 10, 14, 14, 30)
    assert reader.read(Camera('cam', 'C', 'almacen', stream_url='/assets/camaras/tienda.webm'), moment) is not None
    assert frames == [ROOT / 'assets' / 'camaras' / 'tienda.webm'] and frames[0].is_file()
    assert reader.read(Camera('cam', 'C', 'almacen', stream_url='/assets/../data/usuarios.json'), moment) is None
    assert not (tmp_path / 'videos').exists()  # nada que descargar


def test_camera_images_are_fetched_again_each_time_and_errors_mean_no_image(tmp_path: Path) -> None:
    picture = BytesIO()
    Image.new('RGB', (40, 30), (200, 10, 10)).save(picture, 'PNG')
    answers = [httpx.Response(200, content=picture.getvalue()), httpx.Response(404), httpx.Response(200, content=b'x')]

    def server(request: httpx.Request) -> httpx.Response:
        return answers.pop(0)

    reader = VideoFrameReader(tmp_path / 'videos', transport=httpx.MockTransport(server))
    camera = Camera('cam', 'Cámara', 'almacen', stream_url='https://ejemplo.es/camara/foto.jpg')
    image = reader.read(camera, datetime(2026, 10, 14, 14, 30))
    assert image is not None and image.size == (40, 30)
    assert reader.read(camera, datetime(2026, 10, 14, 14, 30)) is None  # 404
    assert reader.read(camera, datetime(2026, 10, 14, 14, 30)) is None  # no es una imagen
    assert answers == []


def test_opencv_takes_the_frame_of_the_current_moment(tmp_path: Path) -> None:
    cv2 = pytest.importorskip('cv2')
    import numpy

    path = tmp_path / 'camara.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (64, 48))
    for index in range(30):  # 3 segundos: rojo, verde y azul
        color = [(0, 0, 255), (0, 255, 0), (255, 0, 0)][index // 10]
        writer.write(numpy.full((48, 64, 3), color, dtype=numpy.uint8))
    writer.release()
    reader = VideoFrameReader(tmp_path / 'videos')
    camera = Camera('cam', 'Cámara', 'almacen', stream_url=str(path))
    second = datetime.fromtimestamp(3 * 1_000_000 + 1.5)  # 1,5 s dentro del bucle de 3 s: verde
    image = reader.read(camera, second)
    assert image is not None and image.size == (64, 48)
    red, green, blue = rgb(image, (32, 24))
    assert green > 200 and red < 60 and blue < 60


@pytest.fixture(scope='module')
def yolo() -> Iterator[YoloPersonDetector]:
    pytest.importorskip('ultralytics')
    detector = YoloPersonDetector()
    try:
        detector.prepare()
    except VisionUnavailableError as error:
        pytest.skip(f'YOLO no disponible: {error}')
    yield detector


def test_real_yolo_finds_the_people_of_the_sample_photo(yolo: YoloPersonDetector) -> None:
    import ultralytics

    with Image.open(Path(ultralytics.__file__).parent / 'assets' / 'bus.jpg') as picture:
        people = yolo.detect(picture.convert('RGB'))
    assert len(people) >= 3
    assert all(0 <= box.left < box.right <= 1 and 0 <= box.top < box.bottom <= 1 for box in people)
    assert all(YoloPersonDetector.CONFIDENCE <= box.confidence <= 1 for box in people)
    assert yolo.detect(Image.new('RGB', (320, 240), (200, 200, 200))) == ()


def test_real_yolo_sees_the_shoppers_of_the_almacen_camera_and_the_rules_react(
    yolo: YoloPersonDetector, data_dir: Path, clock: FixedClock,
) -> None:
    """De principio a fin: vídeo local de la cámara del almacén, OpenCV, YOLO, imagen marcada y reglas."""
    repositories = Repositories.from_json_dir(data_dir)
    quiet_almacen(repositories)
    frames = VideoFrameReader(data_dir / 'videos', local_urls={'/assets': ROOT / 'assets'})
    controller = VisionController(repositories, clock, yolo, frames)
    controller.step()
    almacen = camera(repositories, 'cam-almacen')
    assert almacen.people and almacen.people >= 1 and almacen.capture  # el vídeo muestra clientes en todo momento
    services = Services.create(repositories, clock=clock, detector=FakeDetector(), frames=FakeFrames())
    [alert] = services.rules.evaluate().alerts_created
    assert (alert.type, alert.capture) == (AlertType.PERSON_IN_RESTRICTED_ZONE, almacen.capture)
    led = repositories.actuators.get('led-aviso')
    assert led is not None and led.is_on


def test_the_analysis_script_marks_the_photo_and_the_rules_open_the_alert(
    yolo: YoloPersonDetector, data_dir: Path, clock: FixedClock,
) -> None:
    repositories = Repositories.from_json_dir(data_dir)
    quiet_almacen(repositories)
    output = subprocess.run(
        [sys.executable, 'scripts/analizar_imagen.py', '--datos', str(data_dir), '--camara', 'cam-almacen',
         '--ejemplo'],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert 'Cámara 1 · Almacén: YOLO ve' in output.stdout and 'zona restringida' in output.stdout
    analyzed = camera(repositories, 'cam-almacen')
    assert analyzed.people and analyzed.people >= 3 and analyzed.capture
    services = Services.create(repositories, clock=clock, detector=FakeDetector(), frames=FakeFrames())
    [alert] = services.rules.evaluate().alerts_created
    assert alert.capture == analyzed.capture


def test_the_analysis_script_explains_wrong_arguments(data_dir: Path, tmp_path: Path) -> None:
    command = [sys.executable, 'scripts/analizar_imagen.py', '--datos', str(data_dir)]
    unknown = subprocess.run([*command, '--camara', 'cam-sotano', '--imagen', 'x.jpg'], cwd=ROOT,
                             capture_output=True, text=True, check=False)
    assert unknown.returncode != 0 and 'Cámaras disponibles: cam-almacen, cam-parking' in unknown.stderr
    missing = subprocess.run([*command, '--camara', 'cam-almacen', '--imagen', str(tmp_path / 'nada.jpg')], cwd=ROOT,
                             capture_output=True, text=True, check=False)
    assert missing.returncode != 0 and 'No se puede abrir la imagen' in missing.stderr


# --- Configuración ----------------------------------------------------------------------------------------


def test_the_analysis_can_be_configured_with_environment_variables() -> None:
    defaults = AppSettings.from_env({})
    assert (defaults.vision, defaults.yolo_model) == (True, 'yolo26n.pt')
    custom = AppSettings.from_env({'LUMINA_VISION': 'false', 'LUMINA_YOLO_MODEL': 'yolo26s.pt'})
    assert (custom.vision, custom.yolo_model) == (False, 'yolo26s.pt')
    with pytest.raises(ValueError, match='LUMINA_VISION'):
        AppSettings.from_env({'LUMINA_VISION': 'quizá'})
