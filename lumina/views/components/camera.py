"""Cuadrícula de cámaras: vídeo en directo, imagen o vista simulada, con la detección de su zona.

Cada cámara se construye una sola vez por página: los refrescos de datos solo cambian sus rótulos
(:meth:`CameraGrid.show_feeds`), así el vídeo nunca se reinicia ni parpadea.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar
from urllib.parse import urlparse

from nicegui import ui

from ...models import Camera, CameraFeed, SensorStatus
from ..formatting import Formatter
from ..theme import Theme
from .base import Box, Picture, Text
from .layout import Note, Panel


class CameraTile(Box):
    """Señal de una cámara.

    - URL de vídeo (``.mp4``, ``.webm``…): reproducción continua, sin sonido ni controles, con el
      rótulo «EN DIRECTO» y la hora actual sobreimpresa, como un monitor de videovigilancia.
    - Otra URL: imagen o flujo MJPEG.
    - Sin URL: vista simulada, identificada explícitamente.
    """

    VIDEO_EXTENSIONS: ClassVar[tuple[str, ...]] = ('.mp4', '.m4v', '.webm', '.ogv', '.ogg', '.mov')

    def __init__(self, feed: CameraFeed, today: date, now: datetime) -> None:
        super().__init__()
        self.mark(f'camera-{feed.camera.id}')
        camera = feed.camera
        online = camera.status is SensorStatus.ACTIVE
        self._clock: Text | None = None
        self._live: Text | None = None
        self._no_signal: Box | None = None
        with self:
            if online and camera.stream_url and self.is_video(camera.stream_url):
                self._video_view(camera, now)
            elif online and camera.stream_url:
                with Box(Theme.CAMERA_VIEW):
                    Picture(camera.stream_url, alt=camera.name, classes=Theme.CAMERA_IMAGE)
                    Text(camera.name, classes=Theme.CAMERA_OVERLAY)
            else:
                with Box(Theme.CAMERA_VIEW):
                    Text(camera.name)
                    Text('Vista simulada · Sin vídeo real' if online else 'Cámara sin conexión', classes=Theme.SMALL)
            self._caption = Text(tag='p', classes=Theme.CAMERA_CAPTION)
        self.show_feed(feed, today)

    @classmethod
    def is_video(cls, url: str) -> bool:
        """Las URL de vídeo se reconocen por la extensión del fichero (sin contar la consulta)."""
        return urlparse(url).path.lower().endswith(cls.VIDEO_EXTENSIONS)

    def _video_view(self, camera: Camera, now: datetime) -> None:
        with Box(Theme.CAMERA_SCREEN):
            video = ui.video(camera.stream_url or '', controls=False, autoplay=True, muted=True, loop=True)
            video.classes(Theme.CAMERA_IMAGE).mark(f'video-{camera.id}')
            video.props['playsinline'] = True  # sin pantalla completa automática en móviles
            video.props['disablepictureinpicture'] = True
            video.props['aria-label'] = f'Vídeo en directo de {camera.name}'
            video.on('error', self.signal_lost)
            with Box(Theme.CAMERA_LABEL):
                Box(Theme.CAMERA_LIVE_DOT, tag='span')
                self._live = Text('EN DIRECTO', classes=f'{Theme.STRONG} tracking-wide')
                Text(f'· {camera.name}')
            self._clock = Text(Formatter.camera_time(now), classes=Theme.CAMERA_CLOCK).mark(f'clock-{camera.id}')
            self._no_signal = Box(Theme.CAMERA_NO_SIGNAL)
            with self._no_signal:
                Text('Sin señal de vídeo', classes=Theme.STRONG)
                Text('Comprueba la conexión a Internet', classes=Theme.SMALL)
            self._no_signal.set_visibility(False)

    def show_feed(self, feed: CameraFeed, today: date) -> None:
        """Rótulo inferior: zona, detección agregada y hora de su lectura."""
        self._caption.set_text(
            f'{feed.zone.name} · {feed.motion.label} · {Formatter.moment(feed.motion.updated_at, today)}'
        )

    def show_time(self, now: datetime) -> None:
        """Avanza la hora sobreimpresa en el vídeo."""
        if self._clock is not None:
            self._clock.set_text(Formatter.camera_time(now))

    def signal_lost(self) -> None:
        """El navegador no ha podido reproducir el vídeo (sin conexión o URL no válida)."""
        if self._no_signal is not None and self._live is not None:
            self._no_signal.set_visibility(True)
            self._live.set_text('SIN SEÑAL')


class CameraGrid(Panel):
    """Cámaras del establecimiento, con disposición adaptable de dos columnas."""

    def __init__(self, feeds: tuple[CameraFeed, ...], today: date, now: datetime) -> None:
        super().__init__('Cámaras')
        self._cameras = tuple(feed.camera for feed in feeds)
        self._tiles: dict[str, CameraTile] = {}
        with self:
            if not feeds:
                Note('No hay cámaras configuradas.')
            with Box(Theme.CAMERA_GRID):
                for feed in feeds:
                    self._tiles[feed.camera.id] = CameraTile(feed, today, now)

    def shows(self, feeds: tuple[CameraFeed, ...]) -> bool:
        """``True`` si la cuadrícula se construyó para estas mismas cámaras (con la misma señal y estado)."""
        return self._cameras == tuple(feed.camera for feed in feeds)

    def show_feeds(self, feeds: tuple[CameraFeed, ...], today: date) -> None:
        """Actualiza los rótulos sin tocar los vídeos."""
        for feed in feeds:
            tile = self._tiles.get(feed.camera.id)
            if tile is not None:
                tile.show_feed(feed, today)

    def show_time(self, now: datetime) -> None:
        for tile in self._tiles.values():
            tile.show_time(now)
