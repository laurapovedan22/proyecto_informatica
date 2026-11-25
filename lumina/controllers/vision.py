"""Análisis de imagen de las cámaras con YOLO: personas en zonas restringidas (ampliación del 18/11/2026).

Funciona como un sensor más. En cada ciclo se toma un fotograma de cada cámara, YOLO cuenta las
personas que se ven y el resultado se guarda en la propia cámara (``sensores.json`` › ``camaras``)
con la imagen marcada. Las reglas (:class:`~lumina.controllers.rules.RulesController`) lo tratan
igual que el movimiento: si la zona de la cámara es restringida, encienden el LED y la alarma de
la zona y abren una alerta con esa imagen.

Este módulo no importa NiceGUI, YOLO ni OpenCV: las piezas reales están en :mod:`.yolo` (y solo
se cargan al usarse) y los tests usan otras de prueba.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ..models import Camera, SensorStatus, SystemConfig, VisionState, VisionStatus, Zone
from ..repositories import Repositories
from .analysis import FacilityAnalyzer
from .clock import Clock
from .errors import NotFoundError

if TYPE_CHECKING:
    from PIL.Image import Image
    from PIL.ImageDraw import ImageDraw
    from PIL.ImageFont import FreeTypeFont, ImageFont

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PersonBox:
    """Persona detectada: recuadro en coordenadas relativas a la imagen (de 0 a 1) y confianza (de 0 a 1)."""

    left: float
    top: float
    right: float
    bottom: float
    confidence: float


class VisionUnavailableError(RuntimeError):
    """No se puede analizar: falta ultralytics u OpenCV, o no se ha podido cargar el modelo."""


class PersonDetector(ABC):
    """Detector de personas en una imagen (en Lumina, YOLO)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del modelo que se muestra en pantalla (``YOLO26n``)."""

    def prepare(self) -> None:  # noqa: B027 - opcional: no todos los detectores tienen que cargar nada
        """Carga el modelo si aún no lo está; lanza :class:`VisionUnavailableError` si no se puede."""

    @abstractmethod
    def detect(self, image: Image) -> tuple[PersonBox, ...]:
        """Personas que se ven en la imagen."""


class FrameReader(ABC):
    """Fuente de fotogramas de las cámaras."""

    @abstractmethod
    def read(self, camera: Camera, now: datetime) -> Image | None:
        """Fotograma de la cámara en este momento, o ``None`` si ahora no hay imagen (sin señal…)."""


class CapturePainter:
    """Marca en el fotograma lo que ha visto YOLO, como el monitor de un vigilante.

    Recuadra a cada persona con su confianza y rotula arriba «PERSONA EN ZONA RESTRINGIDA» (en
    rojo) o las personas vistas (en verde, si la zona no es restringida); abajo, cámara y hora.
    """

    ALERT: ClassVar[tuple[int, int, int]] = (229, 72, 77)
    """El rojo del piloto «EN DIRECTO» de las cámaras."""
    CALM: ClassVar[tuple[int, int, int]] = (70, 99, 71)
    """El verde de la paleta de Lumina."""
    DARK: ClassVar[tuple[int, int, int]] = (16, 18, 16)
    WHITE: ClassVar[tuple[int, int, int]] = (255, 255, 255)
    MAX_WIDTH = 960
    QUALITY = 85
    FONTS: ClassVar[tuple[str, ...]] = ('DejaVuSans.ttf', 'Arial.ttf', 'arial.ttf', 'LiberationSans-Regular.ttf')
    """Fuentes del sistema con tildes y eñes (Linux, macOS y Windows) si no está la de matplotlib."""
    _fonts: ClassVar[dict[int, ImageFont | FreeTypeFont]] = {}

    @classmethod
    def font(cls, size: int) -> ImageFont | FreeTypeFont:
        """Fuente de los rótulos, con tildes y eñes.

        La que trae Pillow no las tiene («Almacén» saldría «Almac□n»): se usa DejaVu Sans, que llega con
        matplotlib al instalar ultralytics, o la primera de :attr:`FONTS` que tenga el sistema. La de
        Pillow queda como último recurso. Se carga una sola vez por tamaño.
        """
        cached = cls._fonts.get(size)
        if cached is not None:
            return cached
        from PIL import ImageFont as Fonts

        chosen: ImageFont | FreeTypeFont | None = None
        for candidate in cls._font_files():
            try:
                chosen = Fonts.truetype(candidate, size)
                break
            except OSError:  # no está en este equipo
                continue
        if chosen is None:
            chosen = Fonts.load_default(size=size)
        cls._fonts[size] = chosen
        return chosen

    @classmethod
    def _font_files(cls) -> list[str]:
        """DejaVu Sans de matplotlib (sin importarlo) y, después, las fuentes del sistema."""
        files = list(cls.FONTS)
        matplotlib = importlib.util.find_spec('matplotlib')
        if matplotlib is not None and matplotlib.origin is not None:
            files.insert(0, str(Path(matplotlib.origin).parent / 'mpl-data' / 'fonts' / 'ttf' / 'DejaVuSans.ttf'))
        return files

    @classmethod
    def paint(cls, frame: Image, people: Sequence[PersonBox], camera: Camera, zone: Zone, moment: datetime) -> bytes:
        """Imagen JPEG marcada."""
        from PIL import Image as PillowImage
        from PIL import ImageDraw

        image = frame.convert('RGB')
        if image.width > cls.MAX_WIDTH:
            height = round(image.height * cls.MAX_WIDTH / image.width)
            image = image.resize((cls.MAX_WIDTH, height), PillowImage.Resampling.LANCZOS)
        draw = ImageDraw.Draw(image)
        font = cls.font(max(12, round(image.width / 45)))
        color = cls.ALERT if zone.restricted else cls.CALM
        line = max(2, round(image.width / 300))
        for person in people:
            box = (
                person.left * image.width,
                person.top * image.height,
                person.right * image.width,
                person.bottom * image.height,
            )
            draw.rectangle(box, outline=color, width=line)
            cls._label(draw, font, (box[0], box[1]), f'Persona {round(person.confidence * 100)} %', color, above=True)
        seen = '1 persona' if len(people) == 1 else f'{len(people)} personas'
        title = f'PERSONA EN ZONA RESTRINGIDA · {zone.name}' if zone.restricted else f'{seen} · {zone.name}'
        margin = line * 3
        cls._label(draw, font, (margin, margin), title, color)
        footer = f'{moment:%d/%m/%Y %H:%M:%S} · {camera.name} · {seen}'
        width = draw.textbbox((0, 0), footer, font=font)[2]
        cls._label(draw, font, (image.width - width - 3 * margin, image.height - 3 * margin), footer, cls.DARK,
                   above=True)
        output = BytesIO()
        image.save(output, 'JPEG', quality=cls.QUALITY)
        return output.getvalue()

    @classmethod
    def _label(
        cls,
        draw: ImageDraw,
        font: ImageFont | FreeTypeFont,
        corner: tuple[float, float],
        text: str,
        color: tuple[int, int, int],
        *,
        above: bool = False,
    ) -> None:
        """Texto blanco sobre una franja de color; ``above`` lo coloca encima de la esquina dada."""
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        pad = max(2, round((bottom - top) / 4))
        width, height = right - left + 2 * pad, bottom - top + 2 * pad
        x = max(corner[0], 0)
        y = max(corner[1] - height, 0) if above else corner[1]
        draw.rectangle((x, y, x + width, y + height), fill=color)
        draw.text((x + pad - left, y + pad - top), text, fill=cls.WHITE, font=font)


class VisionController:
    """Ciclo del análisis de imagen; :class:`lumina.app.LuminaApp` lo ejecuta en segundo plano.

    Si otra fuente escribe el análisis de una cámara (``scripts/analizar_imagen.py`` o la maqueta),
    se lo deja durante :attr:`EXTERNAL_HOLD`, igual que la simulación en vivo con los sensores.
    """

    EXTERNAL_HOLD: ClassVar[timedelta] = timedelta(minutes=2)
    CAPTURE_LIFETIME: ClassVar[timedelta] = timedelta(minutes=2)
    """Antigüedad a partir de la cual se borra una captura que ya no usan ni las cámaras ni las alertas."""
    RETRY_AFTER: ClassVar[timedelta] = timedelta(minutes=1)
    """Espera antes de volver a intentarlo si no se ha podido cargar YOLO."""

    def __init__(self, repositories: Repositories, clock: Clock, detector: PersonDetector, frames: FrameReader) -> None:
        self._repositories = repositories
        self._clock = clock
        self._detector = detector
        self._frames = frames
        self._lock = threading.RLock()
        self._status = VisionStatus()
        self._retry_at: datetime | None = None
        self._written: dict[str, Camera] = {}
        """Último análisis que ha guardado este controlador de cada cámara (para notar escrituras ajenas)."""
        self._held_until: dict[str, datetime] = {}

    @property
    def status(self) -> VisionStatus:
        return self._status

    def step(self) -> list[Camera]:
        """Analiza un fotograma de cada cámara activa con señal y devuelve las cámaras guardadas."""
        with self._lock:
            now = self._clock.now()
            if self._retry_at is not None and now < self._retry_at:
                return []
            saved: list[Camera] = []
            try:
                self._detector.prepare()
                config = self._repositories.config.load()
                for camera in self._repositories.cameras.list_all():
                    if camera.status is not SensorStatus.ACTIVE or not camera.stream_url or self._held(camera, now):
                        continue
                    frame = self._frames.read(camera, now)
                    result = self._save(camera, frame, config, now)
                    if result is not None:
                        saved.append(result)
            except VisionUnavailableError as error:
                if self._status.detail != str(error):
                    log.warning('Análisis de imagen no disponible: %s', error)
                self._status = VisionStatus(VisionState.UNAVAILABLE, str(error))
                self._retry_at = now + self.RETRY_AFTER
                return saved
            self._status = VisionStatus(VisionState.READY, self._detector.name)
            self._retry_at = None
            self._clean_up(now)
            return saved

    def analyze(self, camera_id: str, image: Image) -> Camera:
        """Analiza una imagen concreta como si la hubiera captado la cámara (``scripts/analizar_imagen.py``)."""
        with self._lock:
            camera = self._repositories.cameras.get(camera_id)
            if camera is None:
                raise NotFoundError(f'No existe la cámara «{camera_id}».')
            saved = self._save(camera, image, self._repositories.config.load(), self._clock.now())
            if saved is None:
                raise NotFoundError(f'La cámara «{camera_id}» ya no existe.')
            return saved

    def _save(self, camera: Camera, frame: Image | None, config: SystemConfig, now: datetime) -> Camera | None:
        """Guarda el análisis del fotograma (``None``: sin imagen, así que no se sabe si hay alguien)."""
        people = self._detector.detect(frame) if frame is not None else ()
        capture: str | None = None
        if frame is not None and people:
            zone = FacilityAnalyzer.zone(config, camera.zone_id)
            image = CapturePainter.paint(frame, people, camera, zone, now)
            capture = self._repositories.captures.save(camera.id, now, image)
        count = len(people) if frame is not None else None
        saved = self._repositories.cameras.modify(camera.id, lambda current: current.with_analysis(count, now, capture))
        if saved is not None:
            self._written[camera.id] = saved
        return saved

    def _held(self, current: Camera, now: datetime) -> bool:
        """``True`` mientras otra fuente controla el análisis de la cámara."""
        written = self._written.get(current.id)
        if written is not None and current.analysis != written.analysis:
            self._held_until[current.id] = now + self.EXTERNAL_HOLD
            self._written[current.id] = current
        until = self._held_until.get(current.id)
        if until is None:
            return False
        if now < until:
            return True
        del self._held_until[current.id]
        return False

    def _clean_up(self, now: datetime) -> None:
        """Borra las capturas antiguas que ya no muestra ninguna cámara ni ninguna alerta."""
        keep = {camera.capture for camera in self._repositories.cameras.list_all() if camera.capture}
        keep |= {alert.capture for alert in self._repositories.alerts.list_all() if alert.capture}
        self._repositories.captures.remove_unused(keep, now - self.CAPTURE_LIFETIME)
