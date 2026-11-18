"""Piezas reales del análisis de imagen: YOLO (paquete ``ultralytics``) y fotogramas con OpenCV.

Son las únicas que importan esas bibliotecas, y lo hacen la primera vez que se usan: sin ellas
Lumina funciona igual, pero sin análisis de imagen (es lo que pasa en el ejecutable).
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections.abc import Mapping
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import unquote, urlparse

import httpx

from ..models import Camera
from ..settings import DOWNLOADS_DIR
from .vision import FrameReader, PersonBox, PersonDetector, VisionUnavailableError

if TYPE_CHECKING:
    from PIL.Image import Image

log = logging.getLogger(__name__)


class YoloPersonDetector(PersonDetector):
    """Personas (clase 0 de COCO) con un modelo YOLO preentrenado de ultralytics.

    ``model`` es el nombre de un modelo de ultralytics (``yolo26n.pt``, el más ligero), que se
    descarga la primera vez en ``folder``, o la ruta de un fichero ``.pt``. Se desactivan la
    telemetría, las comprobaciones de versión y las instalaciones automáticas de ultralytics.
    """

    PERSON_CLASS = 0
    CONFIDENCE = 0.5
    ENVIRONMENT: ClassVar[dict[str, str]] = {'YOLO_OFFLINE': '1', 'YOLO_VERBOSE': 'false', 'YOLO_AUTOINSTALL': 'false'}

    def __init__(
        self, model: str = 'yolo26n.pt', folder: Path = DOWNLOADS_DIR, *, confidence: float = CONFIDENCE,
    ) -> None:
        self._model_name = model
        self._folder = folder
        self._confidence = confidence
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        stem = Path(self._model_name).stem
        return f'YOLO{stem[4:]}' if stem.lower().startswith('yolo') else stem

    def prepare(self) -> None:
        self._load()

    def detect(self, image: Image) -> tuple[PersonBox, ...]:
        result = self._load().predict(image, classes=[self.PERSON_CLASS], conf=self._confidence, verbose=False)[0]
        boxes = zip(result.boxes.xyxyn.tolist(), result.boxes.conf.tolist(), strict=True)
        return tuple(
            PersonBox(float(left), float(top), float(right), float(bottom), float(confidence))
            for (left, top, right, bottom), confidence in boxes
        )

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                for variable, value in self.ENVIRONMENT.items():
                    os.environ.setdefault(variable, value)  # antes de importar ultralytics, que las lee al cargarse
                try:
                    from ultralytics import YOLO
                except ImportError as error:
                    message = 'falta el paquete ultralytics (pip install -r requirements.txt)'
                    raise VisionUnavailableError(message) from error
                path = Path(self._model_name).expanduser()
                if not path.is_file():
                    self._folder.mkdir(parents=True, exist_ok=True)
                    path = self._folder / path.name  # ultralytics lo descarga ahí si no está
                try:
                    self._model = YOLO(str(path))
                except Exception as error:  # descarga fallida, fichero dañado o modelo desconocido
                    raise VisionUnavailableError(f'no se ha podido cargar el modelo {path.name} ({error})') from error
            return self._model


class VideoFrameReader(FrameReader):
    """Fotograma «en directo» de cada cámara.

    - **Vídeo local**: una dirección de la propia aplicación (``/assets/camaras/tienda.webm``, según
      ``local_urls``), una ruta o ``file://``. Se toma el fotograma que corresponde a la hora actual,
      con el vídeo en bucle, como en pantalla.
    - **Vídeo de Internet**: se descarga una vez, en segundo plano, a ``folder`` y después se trata
      como uno local. Algunos servidores (Wikimedia, por ejemplo) rechazan las descargas automáticas:
      por eso las cámaras de ejemplo usan copias locales de sus vídeos.
    - **Imagen** (JPEG, PNG…): se vuelve a pedir en cada ciclo, por si la cámara la renueva.

    Las descargas usan httpx (lo trae NiceGUI) con sus certificados raíz (certifi): así también
    funcionan con el Python de python.org en macOS, que no usa los del sistema. ``transport``
    permite sustituir la red en los tests.
    """

    USER_AGENT = 'Lumina/0.3 (proyecto universitario de supervision IoT; httpx)'
    TIMEOUT = 30.0
    MAX_VIDEO_BYTES = 200_000_000
    MAX_IMAGE_BYTES = 20_000_000

    def __init__(
        self,
        folder: Path = DOWNLOADS_DIR / 'videos',
        *,
        local_urls: Mapping[str, Path] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """``local_urls`` relaciona direcciones que sirve la aplicación con su carpeta (``/assets`` → ``assets/``)."""
        self._folder = folder
        self._local_urls = {prefix.rstrip('/') + '/': path for prefix, path in (local_urls or {}).items()}
        self._transport = transport
        self._lock = threading.Lock()
        self._downloads: dict[str, threading.Thread] = {}
        self._reported: dict[str, str] = {}

    def read(self, camera: Camera, now: datetime) -> Image | None:
        url = camera.stream_url
        if not url:
            return None
        try:
            if Camera.is_video_url(url):
                video = self._video(url)
                frame = self._video_frame(video, now) if video is not None else None
            else:
                frame = self._picture(url)
        except (OSError, ValueError) as error:  # sin conexión, URL o fichero no válidos
            self._report(camera, str(error))
            return None
        self._reported.pop(camera.id, None)
        return frame

    def wait_for_downloads(self, timeout: float | None = None) -> None:
        """Espera a que terminen las descargas en curso (para los tests y la línea de órdenes)."""
        for thread in list(self._downloads.values()):
            thread.join(timeout)

    # --- Vídeo ---------------------------------------------------------------------------------

    def _video(self, url: str) -> Path | None:
        """Fichero local del vídeo; ``None`` mientras se descarga."""
        local = self._local_path(url)
        if local is not None:
            return local
        target = self._folder / (hashlib.sha256(url.encode('utf-8')).hexdigest()[:16] + Path(urlparse(url).path).suffix)
        if target.is_file():
            return target
        with self._lock:
            thread = self._downloads.get(url)
            if thread is None or not thread.is_alive():
                thread = threading.Thread(target=self._download_video, args=(url, target), daemon=True)
                self._downloads[url] = thread
                thread.start()
        return None

    def _download_video(self, url: str, target: Path) -> None:
        try:
            data = self._download(url, self.MAX_VIDEO_BYTES)
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f'.{target.name}.parcial')
            partial.write_bytes(data)
            os.replace(partial, target)
            log.info('Vídeo descargado para el análisis de imagen: %s', target.name)
        except (OSError, ValueError) as error:
            log.warning('No se ha podido descargar el vídeo %s: %s', url, error)

    @staticmethod
    def _video_frame(path: Path, now: datetime) -> Image:
        cv2 = VideoFrameReader._opencv()
        from PIL import Image as PillowImage

        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                raise OSError(f'OpenCV no puede abrir el vídeo {path.name}')
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps > 0 and frames > 0:  # el fotograma de este momento, con el vídeo en bucle
                capture.set(cv2.CAP_PROP_POS_MSEC, now.timestamp() % (frames / fps) * 1000)
            ok, frame = capture.read()
            if not ok:  # la duración que da el contenedor puede ser aproximada: se vuelve al principio
                capture.set(cv2.CAP_PROP_POS_MSEC, 0)
                ok, frame = capture.read()
            if not ok:
                raise OSError(f'No se ha podido leer ningún fotograma de {path.name}')
            image: Image = PillowImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            return image
        finally:
            capture.release()

    @staticmethod
    def _opencv() -> Any:
        try:
            import cv2
        except ImportError as error:
            message = 'falta OpenCV (se instala con ultralytics: pip install -r requirements.txt)'
            raise VisionUnavailableError(message) from error
        return cv2

    # --- Imagen --------------------------------------------------------------------------------

    def _picture(self, url: str) -> Image:
        from PIL import Image as PillowImage

        local = self._local_path(url)
        data = local.read_bytes() if local is not None else self._download(url, self.MAX_IMAGE_BYTES)
        with PillowImage.open(BytesIO(data)) as picture:
            return picture.convert('RGB')

    # --- Utilidades ----------------------------------------------------------------------------

    def _local_path(self, url: str) -> Path | None:
        """Ruta de un fichero local (de la aplicación, ruta o ``file://``); ``None`` si es una URL de Internet."""
        for prefix, folder in self._local_urls.items():
            if url.startswith(prefix):
                relative = Path(unquote(urlparse(url).path.removeprefix(prefix)))
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError(f'Dirección no válida: {url}')
                return folder / relative
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            return None
        if parsed.scheme == 'file':
            return Path(unquote(parsed.path))
        if parsed.scheme and len(parsed.scheme) > 1:  # «C:» en Windows no es un esquema
            raise ValueError(f'Esquema de URL no admitido: {parsed.scheme}')
        return Path(url).expanduser()

    def _download(self, url: str, limit: int) -> bytes:
        """Contenido de una URL http(s) (las demás se rechazan en :meth:`_local_path`)."""
        data = bytearray()
        try:
            with httpx.Client(
                transport=self._transport,
                headers={'User-Agent': self.USER_AGENT},
                timeout=self.TIMEOUT,
                follow_redirects=True,
            ) as client, client.stream('GET', url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    data += chunk
                    if len(data) > limit:
                        raise ValueError(f'El fichero de {url} es demasiado grande')
        except httpx.HTTPError as error:
            raise OSError(f'No se ha podido descargar {url} ({error})') from error
        return bytes(data)

    def _report(self, camera: Camera, problem: str) -> None:
        """Avisa en el registro una sola vez de cada problema de una cámara, no en cada ciclo."""
        if self._reported.get(camera.id) != problem:
            self._reported[camera.id] = problem
            log.warning('Sin imagen de %s para el análisis: %s', camera.name, problem)
