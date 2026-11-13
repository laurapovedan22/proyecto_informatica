"""Arranque de Lumina como aplicación de escritorio, desde el código o desde el ejecutable.

Prepara el proceso antes de importar NiceGUI, que lee algunas variables al cargarse:

- **Una sola Lumina por carpeta de datos.** Dos procesos escribiendo los mismos JSON podrían
  perder cambios, así que el segundo avisa y no arranca.
- **Sesiones.** En la ventana de escritorio la sesión dura lo que la ventana: la cookie se
  firma con una clave aleatoria y NiceGUI guarda las sesiones en una carpeta propia de la
  carpeta de datos, que se vacía al arrancar y se borra al salir. Las dos se publican como
  variables de entorno para que los procesos auxiliares de NiceGUI (la ventana y la recarga
  en caliente) usen las mismas.
- **Datos.** Una carpeta de datos nueva se rellena con los datos de ejemplo; así el
  ejecutable funciona la primera vez sin preparar nada.
- **Diagnóstico.** El ejecutable no tiene terminal, de modo que los mensajes y los errores se
  guardan en ``lumina.log`` (los de la ventana, en ``lumina-ventana.log``) junto a los datos.

Ni este módulo ni los que importa cargan NiceGUI (lo comprueba ``tests/test_desktop.py``).
"""

from __future__ import annotations

import atexit
import hashlib
import logging
import multiprocessing
import multiprocessing.spawn
import os
import secrets
import shutil
import sys
import threading
from collections.abc import MutableMapping
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import IO

from .settings import APP_NAME, FROZEN, SAMPLE_DATA_DIR, AppSettings, user_data_root

log = logging.getLogger(__name__)


class AlreadyRunningError(RuntimeError):
    """Otra Lumina está usando ya la misma carpeta de datos."""


class Launcher:
    """Prepara el entorno del proceso y arranca :class:`lumina.app.LuminaApp`."""

    SECRET_VARIABLE = 'LUMINA_STORAGE_SECRET'
    STORAGE_VARIABLE = 'NICEGUI_STORAGE_PATH'
    """Carpeta donde NiceGUI guarda las sesiones (``.nicegui`` en la carpeta de trabajo si no se indica)."""

    def __init__(self, environ: MutableMapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ
        self._lock: InstanceLock | None = None

    @staticmethod
    def prepare_auxiliary_process() -> None:
        """En el ejecutable, guarda en un fichero los errores de los procesos auxiliares (la ventana).

        Hay que llamarlo antes de ``freeze_support()``, que desvía esos procesos sin pasar por
        :meth:`run`; en los demás casos no hace nada.
        """
        if FROZEN and multiprocessing.spawn.is_forking(sys.argv):
            DiagnosticsLog(user_data_root() / 'lumina-ventana.log').install(capture_output=True)

    def run(self) -> None:
        try:
            settings = self.prepare()
        except AlreadyRunningError as error:
            log.warning('%s', error)
            self._tell_user(str(error))
            raise SystemExit(1) from error
        from .app import LuminaApp  # NiceGUI se importa cuando el entorno ya está listo

        LuminaApp(settings).run()

    def prepare(self) -> AppSettings:
        """Prepara el proceso y devuelve la configuración con la que debe arrancar.

        Lanza :class:`AlreadyRunningError` si otra Lumina usa la misma carpeta de datos.
        """
        if FROZEN:
            DiagnosticsLog(user_data_root(self._environ) / 'lumina.log').install()
        settings = AppSettings.from_env(self._environ)
        main_process = multiprocessing.current_process().name == 'MainProcess'
        # Los procesos auxiliares de NiceGUI vuelven a ejecutar main.py: el bloqueo y la carpeta de
        # sesiones son del principal. (Como en NiceGUI, se mira el nombre del proceso, porque
        # parent_process() aún es None mientras «spawn» importa main.py en el hijo.)
        if main_process:
            self._lock = InstanceLock(settings.data_dir)
            if not self._lock.acquire():
                self._lock = None
                raise AlreadyRunningError(f'{APP_NAME} ya está abierta con la carpeta de datos {settings.data_dir}.')
        settings = self._prepare_sessions(settings, main_process=main_process)
        DataFolder(settings.data_dir).fill_from(SAMPLE_DATA_DIR)
        return settings

    def release(self) -> None:
        """Libera la carpeta de datos. Al terminar el proceso el sistema lo hace solo, aunque sea de golpe."""
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def _prepare_sessions(self, settings: AppSettings, *, main_process: bool) -> AppSettings:
        if settings.native:
            if not self._environ.get(self.SECRET_VARIABLE, '').strip():
                self._environ[self.SECRET_VARIABLE] = secrets.token_urlsafe(32)
            settings = replace(settings, storage_secret=self._environ[self.SECRET_VARIABLE].strip())
        if not self._environ.get(self.STORAGE_VARIABLE) and main_process:
            folder = self._session_folder(settings)
            if folder is not None:
                self._environ[self.STORAGE_VARIABLE] = str(folder)
        return settings

    def _session_folder(self, settings: AppSettings) -> Path | None:
        sessions = user_data_root(self._environ) / 'sesiones'
        if settings.native:
            # Una carpeta por carpeta de datos, propia del usuario. Con el bloqueo ya conseguido nadie
            # más la usa: se vacía por si una ejecución anterior terminó de golpe y se borra al salir.
            key = hashlib.sha256(str(settings.data_dir.resolve()).encode('utf-8')).hexdigest()[:16]
            folder = sessions / f'escritorio-{key}'
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            atexit.register(shutil.rmtree, folder, ignore_errors=True)
            return folder
        if FROZEN:  # el ejecutable sirviendo al navegador: sesiones persistentes junto a los datos
            return sessions
        return None

    @staticmethod
    def _tell_user(message: str) -> None:
        print(message, file=sys.stderr)
        if sys.platform == 'win32' and FROZEN:  # sin consola: un aviso en pantalla
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x40)


class InstanceLock:
    """Bloqueo de una carpeta de datos para que solo la use una Lumina a la vez.

    Es un bloqueo del sistema sobre ``.lumina.lock``: si el proceso termina, aunque sea de golpe,
    el sistema lo libera y la siguiente ejecución puede arrancar.
    """

    FILE_NAME = '.lumina.lock'

    def __init__(self, folder: Path) -> None:
        self._path = folder / self.FILE_NAME
        self._handle: IO[bytes] | None = None

    def acquire(self) -> bool:
        """``True`` si consigue el bloqueo; ``False`` si lo tiene otro proceso."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open('a+b')
        try:
            if sys.platform == 'win32':
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            self._handle.close()  # cerrar el fichero libera el bloqueo
            self._handle = None


class DataFolder:
    """Carpeta con los ficheros JSON de la aplicación."""

    MARKER = '.inicializando'
    """Marca que existe mientras se copian los datos de ejemplo (si sigue ahí, la copia se interrumpió)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def is_empty(self) -> bool:
        """``True`` si no existe o solo contiene ficheros ocultos (``.DS_Store``, el bloqueo…)."""
        if not self._path.exists():
            return True
        if not self._path.is_dir():
            return False
        return all(item.name.startswith('.') for item in self._path.iterdir())

    def fill_from(self, samples: Path) -> bool:
        """Copia los JSON de ``samples`` en la carpeta si está vacía. Devuelve si ha copiado algo.

        Una carpeta que ya tiene datos nunca se modifica. Mientras se copia hay una marca: si la
        copia se interrumpe, la siguiente ejecución la completa sin tocar lo que ya se copió.
        """
        if not samples.is_dir() or self._path.resolve() == samples.resolve():
            return False
        marker = self._path / self.MARKER
        if not (self.is_empty() or marker.exists()):
            return False
        self._path.mkdir(parents=True, exist_ok=True)
        marker.touch()
        copied = 0
        for sample in sorted(samples.glob('*.json')):
            target = self._path / sample.name
            if sample.name.startswith('.') or target.exists():
                continue
            partial = target.with_name(f'.{target.name}.copia')
            shutil.copyfile(sample, partial)
            os.replace(partial, target)  # cada fichero aparece completo o no aparece
            copied += 1
        marker.unlink()
        if copied:
            log.info('Carpeta de datos nueva: se han copiado %d ficheros de ejemplo en %s', copied, self._path)
        return copied > 0


class DiagnosticsLog:
    """Registro de mensajes y errores en un fichero, para el ejecutable sin terminal."""

    MAX_BYTES = 1_000_000
    BACKUPS = 2

    def __init__(self, path: Path) -> None:
        self._path = path

    def install(self, *, capture_output: bool = False) -> None:
        """Envía al fichero los mensajes de ``logging`` y los errores no capturados.

        ``capture_output`` envía también la salida estándar y de errores: así se guardan las
        trazas que imprime ``multiprocessing`` cuando falla un proceso auxiliar.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if capture_output:
            if self._path.exists() and self._path.stat().st_size > self.MAX_BYTES:
                os.replace(self._path, self._path.with_name(f'{self._path.name}.1'))
            stream = self._path.open('a', encoding='utf-8', buffering=1)
            sys.stdout = sys.stderr = stream
            handler: logging.Handler = logging.StreamHandler(stream)
        else:
            handler = RotatingFileHandler(
                self._path, maxBytes=self.MAX_BYTES, backupCount=self.BACKUPS, encoding='utf-8'
            )
        handler.setFormatter(logging.Formatter(f'%(asctime)s [{os.getpid()}] %(levelname)s %(name)s: %(message)s'))
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        # En Windows, un ejecutable sin consola no tiene sys.stdout ni sys.stderr y uvicorn los usa.
        for name in ('stdout', 'stderr'):
            if getattr(sys, name) is None:
                setattr(sys, name, open(os.devnull, 'w', encoding='utf-8'))  # noqa: SIM115 - abierto hasta salir
        sys.excepthook = self._log_uncaught
        threading.excepthook = self._log_uncaught_in_thread

    @staticmethod
    def _log_uncaught(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
        log.critical('Error no capturado', exc_info=(kind, error, trace))

    @staticmethod
    def _log_uncaught_in_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            log.critical('Error no capturado en el hilo %s', args.thread, exc_info=args.exc_value)
