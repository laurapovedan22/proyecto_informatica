"""Cuadrícula de cámaras: vídeo en directo, imagen o vista simulada, con la detección de su zona.

Cada cámara se construye una sola vez por página: los refrescos de datos solo cambian sus rótulos
(:meth:`CameraGrid.show_feeds`), así el vídeo nunca se reinicia ni parpadea. Bajo cada cámara se
indica lo que ve YOLO; si ve a alguien en una zona restringida se enciende un piloto rojo sobre la
imagen y se puede abrir la imagen analizada, con las personas recuadradas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar

from nicegui import ui

from ...models import Camera, CameraFeed, SensorStatus
from ..formatting import Formatter
from ..theme import Theme, ToneName
from .base import Box, Heading, Picture, StatusText, Text
from .buttons import Button, ButtonVariant
from .layout import Note, Panel


class CameraTile(Box):
    """Señal de una cámara.

    - URL de vídeo (``.mp4``, ``.webm``…): reproducción continua, sin sonido ni controles, con el
      rótulo «EN DIRECTO» y la hora actual sobreimpresa, como un monitor de videovigilancia.
    - Otra URL: imagen o flujo MJPEG.
    - Sin URL: vista simulada, identificada explícitamente.
    """

    VIDEO_EXTENSIONS: ClassVar[tuple[str, ...]] = Camera.VIDEO_EXTENSIONS

    def __init__(self, feed: CameraFeed, today: date, now: datetime) -> None:
        super().__init__()
        self.mark(f'camera-{feed.camera.id}')
        camera = feed.camera
        online = camera.status is SensorStatus.ACTIVE
        self._clock: Text | None = None
        self._live: Text | None = None
        self._no_signal: Box | None = None
        self._capture: str | None = None
        self._capture_caption = ''
        with self:
            if online and camera.stream_url and self.is_video(camera.stream_url):
                self._screen = self._video_view(camera, now)
            elif online and camera.stream_url:
                with Box(Theme.CAMERA_VIEW) as self._screen:
                    Picture(camera.stream_url, alt=camera.name, classes=Theme.CAMERA_IMAGE)
                    Text(camera.name, classes=Theme.CAMERA_OVERLAY)
            else:
                with Box(Theme.CAMERA_VIEW) as self._screen:
                    Text(camera.name)
                    Text('Vista simulada · Sin vídeo real' if online else 'Cámara sin conexión', classes=Theme.SMALL)
            with self._screen:
                self._presence = Box(Theme.CAMERA_PRESENCE).mark(f'presence-{camera.id}')
                self._presence.props['role'] = 'status'
                with self._presence:
                    Box(Theme.CAMERA_PRESENCE_LED, tag='span')
                    Text('PERSONA EN ZONA RESTRINGIDA', classes=f'{Theme.STRONG} tracking-wide')
            self._caption = Text(tag='p', classes=Theme.CAMERA_CAPTION)
            with Box(Theme.CAMERA_VISION):
                self._vision = StatusText(tag='span').mark(f'vision-{camera.id}')
                self._open_capture = Button(
                    'Ver imagen analizada', variant=ButtonVariant.LINK, on_click=self.show_capture
                ).mark(f'open-capture-{camera.id}')
        self.show_feed(feed, today)

    @classmethod
    def is_video(cls, url: str) -> bool:
        """Las URL de vídeo se reconocen por la extensión del fichero (sin contar la consulta)."""
        return Camera.is_video_url(url)

    def _video_view(self, camera: Camera, now: datetime) -> Box:
        with Box(Theme.CAMERA_SCREEN) as screen:
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
        return screen

    def show_feed(self, feed: CameraFeed, today: date) -> None:
        """Rótulos inferiores: detección de la zona y lo último que ha visto YOLO, con sus horas."""
        self._caption.set_text(
            f'{feed.zone.name} · {feed.motion.label} · {Formatter.moment(feed.motion.updated_at, today)}'
        )
        camera = feed.camera
        alarm = feed.restricted_presence
        self._presence.set_visibility(alarm)
        if alarm:
            self._screen.classes(Theme.CAMERA_PRESENCE_FRAME)
        else:
            self._screen.classes(remove=Theme.CAMERA_PRESENCE_FRAME)
        moment = Formatter.moment(camera.analyzed_at, today)
        if camera.people is None:
            text = f'YOLO: sin imagen de la cámara · {moment}' if camera.analyzed_at else 'YOLO: sin analizar'
            self._vision.show(text, ToneName.MUTED)
        else:
            seen = Formatter.people(camera.people)
            if alarm:
                self._vision.show(f'YOLO: {seen} en zona restringida · {moment}', ToneName.DANGER)
            else:
                self._vision.show(f'YOLO: {seen} · {moment}', ToneName.NORMAL)
        self._capture = Formatter.capture_url(camera.capture)
        when = Formatter.camera_time(camera.analyzed_at) if camera.analyzed_at is not None else ''
        self._capture_caption = ' · '.join(part for part in (camera.name, feed.zone.name, when) if part)
        self._open_capture.set_visibility(self._capture is not None)

    def show_time(self, now: datetime) -> None:
        """Avanza la hora sobreimpresa en el vídeo."""
        if self._clock is not None:
            self._clock.set_text(Formatter.camera_time(now))

    def signal_lost(self) -> None:
        """El navegador no ha podido reproducir el vídeo (sin conexión o URL no válida)."""
        if self._no_signal is not None and self._live is not None:
            self._no_signal.set_visibility(True)
            self._live.set_text('SIN SEÑAL')

    async def show_capture(self) -> None:
        """Abre la última imagen analizada, con las personas que ha visto YOLO recuadradas."""
        if self._capture is None:
            return
        with self, ui.dialog() as dialog, Box(Theme.CAPTURE_DIALOG):
            Heading('Imagen analizada por YOLO', level=2)
            Picture(self._capture, alt=f'Imagen analizada de {self._capture_caption}', classes=Theme.CAPTURE_IMAGE)
            Text(self._capture_caption, tag='p', classes=f'{Theme.SMALL} {Theme.MUTED} mb-3')
            with Box(f'{Theme.BUTTON_ROW} justify-end'):
                Button('Cerrar', on_click=lambda: dialog.submit(None))
        await dialog  # se abre y espera a que se cierre
        dialog.delete()


class CameraGrid(Panel):
    """Cámaras del establecimiento, con disposición adaptable de dos columnas."""

    def __init__(self, feeds: tuple[CameraFeed, ...], today: date, now: datetime) -> None:
        super().__init__('Cámaras')
        self._signals = tuple(feed.camera.signal for feed in feeds)
        self._tiles: dict[str, CameraTile] = {}
        with self:
            if not feeds:
                Note('No hay cámaras configuradas.')
            with Box(Theme.CAMERA_GRID):
                for feed in feeds:
                    self._tiles[feed.camera.id] = CameraTile(feed, today, now)
            self._vision = Note('')
            self._vision.mark('vision-status')

    def shows(self, feeds: tuple[CameraFeed, ...]) -> bool:
        """``True`` si la cuadrícula se construyó para estas mismas cámaras (con la misma señal y estado).

        El análisis de YOLO no cuenta: cambia en cada ciclo y solo actualiza los rótulos.
        """
        return self._signals == tuple(feed.camera.signal for feed in feeds)

    def show_feeds(self, feeds: tuple[CameraFeed, ...], today: date) -> None:
        """Actualiza los rótulos sin tocar los vídeos."""
        for feed in feeds:
            tile = self._tiles.get(feed.camera.id)
            if tile is not None:
                tile.show_feed(feed, today)

    def show_vision(self, text: str) -> None:
        """Estado del análisis de imagen, bajo las cámaras."""
        self._vision.set_text(text)

    def show_time(self, now: datetime) -> None:
        for tile in self._tiles.values():
            tile.show_time(now)
