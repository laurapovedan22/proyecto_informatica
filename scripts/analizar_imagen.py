"""Analiza con YOLO una imagen como si la hubiera captado una cámara de Lumina.

Uso, desde la carpeta del proyecto::

    python scripts/analizar_imagen.py --camara cam-almacen --imagen foto.jpg
    python scripts/analizar_imagen.py --camara cam-almacen --ejemplo   # foto de ejemplo de ultralytics

Guarda en la cámara cuántas personas ve YOLO y la imagen con las personas recuadradas, igual que el
análisis en vivo de la aplicación, que se lo deja durante dos minutos. Si la zona de la cámara es
restringida, el siguiente ciclo de reglas de la aplicación enciende el LED y la alarma de la zona y
abre una alerta con la imagen. No arranca la interfaz. Por defecto usa la carpeta de datos de la
aplicación (``datos-locales/``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lumina.controllers import FacilityAnalyzer, LuminaError, SystemClock, VisionController, VisionUnavailableError
from lumina.controllers.yolo import VideoFrameReader, YoloPersonDetector
from lumina.launcher import DataFolder
from lumina.repositories import Repositories
from lumina.settings import DOWNLOADS_DIR, SAMPLE_DATA_DIR, AppSettings


def sample_image() -> Path:
    """Foto de ejemplo con personas que trae ultralytics (un autobús y cuatro peatones)."""
    try:
        import ultralytics
    except ImportError:
        sys.exit('Falta el paquete ultralytics: pip install -r requirements.txt')
    return Path(ultralytics.__file__).resolve().parent / 'assets' / 'bus.jpg'


def main() -> None:
    settings = AppSettings.from_env()
    parser = argparse.ArgumentParser(description='Analiza una imagen con YOLO para una cámara de Lumina.')
    parser.add_argument('--datos', type=Path, default=settings.data_dir, help='carpeta de datos JSON')
    parser.add_argument('--camara', required=True, help='identificador de la cámara (p. ej. cam-almacen)')
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument('--imagen', type=Path, help='fichero de imagen (JPEG, PNG…)')
    origin.add_argument('--ejemplo', action='store_true', help='usar la foto de ejemplo de ultralytics')
    parser.add_argument('--modelo', default=settings.yolo_model, help='modelo de YOLO (por defecto, yolo26n.pt)')
    args = parser.parse_args()

    DataFolder(args.datos).fill_from(SAMPLE_DATA_DIR)  # la misma carpeta de trabajo que usa la aplicación
    repositories = Repositories.from_json_dir(args.datos)
    camera = repositories.cameras.get(args.camara)
    if camera is None:
        cameras = ', '.join(item.id for item in repositories.cameras.list_all()) or 'ninguna'
        parser.error(f'No existe la cámara «{args.camara}». Cámaras disponibles: {cameras}.')
    path: Path = sample_image() if args.ejemplo else args.imagen
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as picture:
            image = picture.convert('RGB')
    except (OSError, UnidentifiedImageError) as error:
        parser.error(f'No se puede abrir la imagen {path}: {error}')

    vision = VisionController(
        repositories, SystemClock(), YoloPersonDetector(args.modelo, DOWNLOADS_DIR), VideoFrameReader()
    )
    try:
        analyzed = vision.analyze(camera.id, image)
    except VisionUnavailableError as error:
        sys.exit(f'No se puede analizar la imagen: {error}.')
    except LuminaError as error:
        sys.exit(str(error))
    zone = FacilityAnalyzer.zone(repositories.config.load(), analyzed.zone_id)
    people = analyzed.people or 0
    print(f'{analyzed.name}: YOLO ve {people} {"persona" if people == 1 else "personas"} en {path.name}.')
    if analyzed.capture:
        print(f'Imagen marcada: {args.datos / analyzed.capture}')
    if people and zone.restricted:
        print(f'{zone.name} es una zona restringida: la aplicación encenderá el LED y la alarma y abrirá la alerta.')
    elif people:
        print(f'{zone.name} no es una zona restringida: no se genera ninguna alerta.')


if __name__ == '__main__':
    main()
