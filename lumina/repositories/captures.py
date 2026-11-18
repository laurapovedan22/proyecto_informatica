"""Capturas del análisis de imagen: ficheros JPEG en la carpeta ``capturas/`` de los datos."""

from __future__ import annotations

import os
import re
import secrets
import tempfile
from collections.abc import Collection
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from .interfaces import CaptureRepository


class FileCaptureRepository(CaptureRepository):
    """Cada imagen es un fichero nuevo: ``capturas/<cámara>-<AAAAMMDD-HHMMSS>-<aleatorio>.jpg``.

    La fecha del nombre es la del análisis (la del reloj de la aplicación), así que la limpieza
    no depende de la fecha de modificación del fichero. Las escrituras son atómicas.
    """

    NAME: ClassVar[re.Pattern[str]] = re.compile(r'^[A-Za-z0-9_-]{1,40}-(\d{8}-\d{6})-[0-9a-f]{6}\.jpg$')

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    @property
    def folder(self) -> Path:
        return self._folder

    def save(self, camera_id: str, moment: datetime, image: bytes) -> str:
        camera = re.sub(r'[^A-Za-z0-9_-]', '-', camera_id)[:40] or 'camara'
        name = f'{camera}-{moment:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}.jpg'
        self._folder.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=self._folder, prefix='.captura-', suffix='.tmp')
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(image)
            os.replace(temporary, self._folder / name)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return f'{self._folder.name}/{name}'

    def path(self, reference: str) -> Path | None:
        folder, _, name = reference.partition('/')
        if folder != self._folder.name or not self.NAME.match(name):
            return None
        return self._folder / name

    def remove_unused(self, keep: Collection[str], older_than: datetime) -> int:
        if not self._folder.is_dir():
            return 0
        kept = {self.path(reference) for reference in keep}
        limit = f'{older_than:%Y%m%d-%H%M%S}'
        removed = 0
        for file in self._folder.glob('*.jpg'):
            match = self.NAME.match(file.name)
            if match is None or file in kept or match.group(1) >= limit:
                continue  # ficheros ajenos, referenciados o recientes: se conservan
            file.unlink(missing_ok=True)
            removed += 1
        return removed
