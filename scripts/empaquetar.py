"""Crea el ejecutable de Lumina (aplicación de escritorio) con PyInstaller.

Uso, desde la carpeta del proyecto y con las dependencias de ``requirements-dev.txt``::

    python scripts/empaquetar.py               # macOS: «dist/Lumina Sprint 1.app» · Windows: carpeta en dist/
    python scripts/empaquetar.py --un-fichero  # Windows/Linux: un único ejecutable (arranca más despacio)

PyInstaller crea el ejecutable del sistema y la arquitectura en los que se ejecuta: para
Windows hay que lanzarlo en Windows y para macOS, en un Mac.

Los JSON de ``data/`` viajan dentro como datos iniciales: la primera vez que se abre, el
ejecutable los copia en la carpeta de datos del usuario y desde entonces trabaja allí.

PyInstaller trabaja en una carpeta temporal propia de cada construcción, que se borra al
terminar, y solo el resultado se copia a ``dist/``: así los ficheros intermedios no se
sincronizan con iCloud/OneDrive y macOS permite firmar la app (iCloud marca los paquetes
``.app`` con atributos que ``codesign`` rechaza).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import nicegui
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lumina import __version__
from lumina.settings import APP_EDITION

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_IDENTIFIER = 'es.lumina.sprint1'


class AppIcon:
    """Icono cuadrado de la aplicación: el logotipo sobre una placa blanca redondeada, como los de macOS."""

    SIZE = 1024
    MARGIN = 100
    """Hueco transparente alrededor de la placa (la placa mide 824 px, la cuadrícula de iconos de macOS)."""
    RADIUS = 185
    PADDING = 110
    """Espacio entre el borde de la placa y el logotipo."""

    def __init__(self, logo: Path) -> None:
        self._logo = logo

    def save(self, target: Path) -> Path:
        canvas = Image.new('RGBA', (self.SIZE, self.SIZE), (0, 0, 0, 0))
        plate = (self.MARGIN, self.MARGIN, self.SIZE - self.MARGIN - 1, self.SIZE - self.MARGIN - 1)
        ImageDraw.Draw(canvas).rounded_rectangle(plate, radius=self.RADIUS, fill=(255, 255, 255, 255))
        with Image.open(self._logo) as source:
            logo = source.convert('RGBA')
        room = self.SIZE - 2 * (self.MARGIN + self.PADDING)
        scale = min(room / logo.width, room / logo.height)
        logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.Resampling.LANCZOS)
        canvas.alpha_composite(logo, ((self.SIZE - logo.width) // 2, (self.SIZE - logo.height) // 2))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target)
        return target


class Packager:
    """Prepara los recursos, llama a PyInstaller y deja el resultado en ``dist/``."""

    DEVELOPMENT_ONLY = ('mypy', 'PIL', 'pytest', '_pytest')
    """Paquetes que PyInstaller arrastraría sin hacer falta: pydantic trae mypy por su plugin y
    NiceGUI usa Pillow solo si está instalado (aquí lo está para crear el icono)."""

    def __init__(self, project: Path, work: Path, *, onefile: bool, clean: bool) -> None:
        self._project = project
        self._work = work
        """Carpeta temporal de esta construcción (fuera del proyecto)."""
        self._onefile = onefile
        self._clean = clean
        self._staging = work / 'dist'
        self._dist = project / 'dist'

    def build(self) -> int:
        icon = AppIcon(self._project / 'assets' / 'logo-icono.png').save(self._work / 'icono-app.png')
        sample_data = self._stage_sample_data()
        command = self.command(icon, sample_data)
        print('Ejecutando PyInstaller:\n ', ' '.join(command), flush=True)
        result = subprocess.run(command, cwd=self._project, check=False)
        if result.returncode != 0:
            return result.returncode
        if self._macos_bundle:
            self._complete_macos_bundle(self.artifact(self._staging))
        target = self._publish()
        print(f'\nListo: {target}')
        return 0

    def command(self, icon: Path, sample_data: Path) -> list[str]:
        command = [
            sys.executable, '-m', 'PyInstaller', str(self._project / 'main.py'),
            '--name', APP_EDITION,
            '--windowed',  # sin terminal: es una aplicación de ventana
            '--noconfirm',
            '--icon', str(icon),
            '--osx-bundle-identifier', BUNDLE_IDENTIFIER,
            '--distpath', str(self._staging),
            '--workpath', str(self._work / 'pyinstaller'),
            '--specpath', str(self._work),
            *self._data(Path(nicegui.__file__).parent, 'nicegui'),  # NiceGUI sirve sus propios ficheros
            *self._data(self._project / 'assets', 'assets'),
            *self._data(sample_data, 'data'),
        ]
        for module in self.DEVELOPMENT_ONLY:
            command += ['--exclude-module', module]
        if self._onefile:
            command.append('--onefile')
        if self._clean:
            command.append('--clean')
        return command

    def artifact(self, folder: Path) -> Path:
        """Lo que se entrega: la ``.app``, la carpeta del programa o el ejecutable único."""
        if self._macos_bundle:
            return folder / f'{APP_EDITION}.app'
        if self._onefile:
            return folder / (APP_EDITION + ('.exe' if sys.platform == 'win32' else ''))
        return folder / APP_EDITION

    @property
    def _macos_bundle(self) -> bool:
        return sys.platform == 'darwin' and not self._onefile

    def _stage_sample_data(self) -> Path:
        """Copia solo los JSON de ``data/`` (sin temporales ni ficheros ocultos)."""
        target = self._work / 'datos-iniciales'
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        for source in sorted((self._project / 'data').glob('*.json')):
            if not source.name.startswith('.'):
                shutil.copyfile(source, target / source.name)
        return target

    def _publish(self) -> Path:
        """Sustituye en ``dist/`` el resultado anterior por el nuevo sin dejarlo nunca a medias.

        Se copia primero a una carpeta provisional junto al destino y después se cambia de sitio
        (un renombrado), de modo que ``dist/`` siempre contiene una versión completa.
        """
        built, target = self.artifact(self._staging), self.artifact(self._dist)
        target.parent.mkdir(parents=True, exist_ok=True)
        provisional = Path(tempfile.mkdtemp(prefix='.publicando-', dir=target.parent))
        incoming, previous = provisional / target.name, provisional / 'anterior'
        clean_up = True
        try:
            self._copy(built, incoming)
            replaced = target.exists() or target.is_symlink()
            if replaced:
                os.replace(target, previous)
            try:
                os.replace(incoming, target)
            except OSError:
                if replaced:
                    try:
                        os.replace(previous, target)  # se deja la versión anterior como estaba
                    except OSError:
                        clean_up = False  # ni eso: la versión anterior se conserva en la carpeta provisional
                        print(f'No se ha podido restaurar la versión anterior; está en {previous}', file=sys.stderr)
                raise
        finally:
            if clean_up:
                shutil.rmtree(provisional, ignore_errors=True)
        return target

    @staticmethod
    def _copy(built: Path, target: Path) -> None:
        if sys.platform == 'darwin':
            subprocess.run(['ditto', str(built), str(target)], check=True)  # conserva enlaces y firmas
        elif built.is_dir():
            shutil.copytree(built, target, symlinks=True)
        else:
            shutil.copy2(built, target)

    @staticmethod
    def _data(source: Path, destination: str) -> list[str]:
        return ['--add-data', f'{source}{os.pathsep}{destination}']

    @staticmethod
    def _complete_macos_bundle(bundle: Path) -> None:
        """Pone la versión en ``Info.plist`` y vuelve a firmar la app (firma local, «ad hoc»)."""
        info_path = bundle / 'Contents' / 'Info.plist'
        with info_path.open('rb') as handle:
            info = plistlib.load(handle)
        info.update(
            CFBundleDisplayName=APP_EDITION,
            CFBundleShortVersionString=__version__,
            CFBundleVersion=__version__,
            LSApplicationCategoryType='public.app-category.business',
            NSHumanReadableCopyright='Proyecto de Ingeniería Informática · Universidad Europea',
        )
        with info_path.open('wb') as handle:
            plistlib.dump(info, handle)
        subprocess.run(['codesign', '--force', '--sign', '-', str(bundle)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='Crea el ejecutable de Lumina con PyInstaller.')
    parser.add_argument(
        '--un-fichero', action='store_true', help='un único ejecutable en lugar de una carpeta (no para macOS)'
    )
    parser.add_argument('--limpiar', action='store_true', help='borra la caché de PyInstaller antes de empezar')
    args = parser.parse_args()
    if importlib.util.find_spec('PyInstaller') is None:
        sys.exit('Falta PyInstaller: pip install -r requirements-dev.txt')
    if args.un_fichero and sys.platform == 'darwin':
        sys.exit(f'En macOS se crea {APP_EDITION}.app; --un-fichero solo es para Windows y Linux.')
    with tempfile.TemporaryDirectory(prefix='lumina-empaquetado-') as work:
        code = Packager(PROJECT_ROOT, Path(work), onefile=args.un_fichero, clean=args.limpiar).build()
    sys.exit(code)


if __name__ == '__main__':
    main()
