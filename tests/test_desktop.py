"""Aplicación de escritorio: configuración, lanzador y datos iniciales del ejecutable."""

from __future__ import annotations

import filecmp
import multiprocessing
import subprocess
import sys
from pathlib import Path

import pytest

from lumina.launcher import AlreadyRunningError, DataFolder, InstanceLock, Launcher
from lumina.settings import SAMPLE_DATA_DIR, AppSettings, user_data_root

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEVELOPMENT_SECRET = AppSettings().storage_secret


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Carpeta personal temporal: el lanzador guarda ahí las sesiones (nunca en la del usuario real)."""
    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))  # macOS y Linux
    monkeypatch.setenv('USERPROFILE', str(home))  # Windows
    monkeypatch.delenv('APPDATA', raising=False)  # que todo cuelgue de la carpeta personal temporal
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    return home


# --- Configuración ----------------------------------------------------------------------------


def test_lumina_opens_in_a_desktop_window_by_default() -> None:
    settings = AppSettings.from_env({})
    assert settings.native
    assert settings.port is None  # NiceGUI busca un puerto libre
    assert not settings.reload


def test_browser_mode_and_port_can_be_chosen() -> None:
    settings = AppSettings.from_env({'LUMINA_NATIVE': 'false', 'LUMINA_PORT': '9000'})
    assert (settings.native, settings.port) == (False, 9000)
    with pytest.raises(ValueError, match='LUMINA_PORT'):
        AppSettings.from_env({'LUMINA_PORT': 'ochenta'})


@pytest.mark.parametrize(
    ('platform', 'environ', 'expected'),
    [
        ('darwin', {}, '~/Library/Application Support/Lumina Sprint 1'),
        ('win32', {'APPDATA': '/perfiles/ana/AppData/Roaming'}, '/perfiles/ana/AppData/Roaming/Lumina Sprint 1'),
        ('linux', {'XDG_DATA_HOME': '/datos'}, '/datos/lumina-sprint-1'),
        ('linux', {}, '~/.local/share/lumina-sprint-1'),
    ],
)
def test_user_data_folder_follows_each_system(platform: str, environ: dict[str, str], expected: str) -> None:
    assert user_data_root(environ, platform=platform) == Path(expected).expanduser()


# --- Datos iniciales del ejecutable -----------------------------------------------------------


def sample_files() -> list[str]:
    return sorted(path.name for path in SAMPLE_DATA_DIR.glob('*.json'))


def test_a_new_data_folder_starts_with_the_sample_data(tmp_path: Path) -> None:
    folder = DataFolder(tmp_path / 'Lumina' / 'data')
    assert folder.fill_from(SAMPLE_DATA_DIR)
    assert sorted(path.name for path in folder.path.iterdir()) == sample_files()
    for name in sample_files():
        assert filecmp.cmp(folder.path / name, SAMPLE_DATA_DIR / name, shallow=False)


def test_a_folder_with_only_hidden_files_counts_as_empty(tmp_path: Path) -> None:
    folder = tmp_path / 'datos'
    folder.mkdir()
    (folder / '.DS_Store').write_bytes(b'')
    assert DataFolder(folder).fill_from(SAMPLE_DATA_DIR)
    assert (folder / 'usuarios.json').is_file()


def test_existing_data_is_never_overwritten(tmp_path: Path) -> None:
    folder = tmp_path / 'datos'
    folder.mkdir()
    users = folder / 'usuarios.json'
    users.write_text('{"usuarios": []}', encoding='utf-8')
    assert not DataFolder(folder).fill_from(SAMPLE_DATA_DIR)
    assert [path.name for path in folder.iterdir()] == ['usuarios.json']
    assert users.read_text(encoding='utf-8') == '{"usuarios": []}'


def test_an_interrupted_first_copy_is_completed(tmp_path: Path) -> None:
    folder = tmp_path / 'datos'
    folder.mkdir()
    (folder / DataFolder.MARKER).touch()  # la primera ejecución se cortó a medias
    already_copied = folder / 'actuadores.json'
    already_copied.write_text('{"actuadores": []}', encoding='utf-8')
    assert DataFolder(folder).fill_from(SAMPLE_DATA_DIR)
    assert sorted(path.name for path in folder.iterdir()) == sample_files()  # y ya sin la marca
    assert already_copied.read_text(encoding='utf-8') == '{"actuadores": []}'


def test_the_sample_folder_is_not_copied_onto_itself() -> None:
    assert not DataFolder(SAMPLE_DATA_DIR).fill_from(SAMPLE_DATA_DIR)


# --- Una sola Lumina por carpeta de datos -----------------------------------------------------


def test_a_data_folder_can_only_be_locked_once(tmp_path: Path) -> None:
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_a_second_lumina_on_the_same_data_does_not_start(data_dir: Path) -> None:
    environ = {'LUMINA_DATA_DIR': str(data_dir)}
    running = Launcher(environ)
    running.prepare()
    open_session = Path(environ['NICEGUI_STORAGE_PATH']) / 'storage-user-abierta.json'
    open_session.write_text('{"user_id": "usr-ana"}', encoding='utf-8')
    try:
        with pytest.raises(AlreadyRunningError, match='ya está abierta'):
            Launcher({'LUMINA_DATA_DIR': str(data_dir)}).prepare()
        assert open_session.exists()  # no toca nada de la que está abierta
    finally:
        running.release()
    after_closing = Launcher({'LUMINA_DATA_DIR': str(data_dir)})
    after_closing.prepare()
    after_closing.release()


# --- Sesiones ---------------------------------------------------------------------------------


def test_desktop_sessions_last_one_run(data_dir: Path) -> None:
    environ = {'LUMINA_DATA_DIR': str(data_dir)}
    launcher = Launcher(environ)
    try:
        settings = launcher.prepare()
        storage = Path(environ['NICEGUI_STORAGE_PATH'])
        assert settings.native
        assert settings.storage_secret == environ['LUMINA_STORAGE_SECRET'] != DEVELOPMENT_SECRET
        assert len(settings.storage_secret) >= 32
        assert storage.is_dir() and not any(storage.iterdir())
        assert storage.is_relative_to(user_data_root())  # carpeta del usuario, no un /tmp compartido
        (storage / 'storage-user-antigua.json').write_text('{"user_id": "usr-ana"}', encoding='utf-8')
    finally:
        launcher.release()  # como si la ejecución hubiera terminado de golpe
    next_run = {'LUMINA_DATA_DIR': str(data_dir)}
    launcher = Launcher(next_run)
    try:
        assert launcher.prepare().storage_secret != settings.storage_secret  # las cookies de antes no valen
        assert next_run['NICEGUI_STORAGE_PATH'] == str(storage)
        assert not any(storage.iterdir())  # ni las sesiones que quedaron
    finally:
        launcher.release()


def test_auxiliary_processes_reuse_the_main_process_sessions(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {'LUMINA_DATA_DIR': str(data_dir)}
    main = Launcher(environ)
    try:
        settings = main.prepare()
        monkeypatch.setattr(multiprocessing.current_process(), 'name', 'SpawnProcess-1')
        inherited = dict(environ)  # el proceso hijo hereda el entorno del principal
        assert Launcher(inherited).prepare().storage_secret == settings.storage_secret  # sin bloquear nada
        assert inherited == environ
    finally:
        main.release()


def test_auxiliary_processes_never_create_a_session_folder(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si un proceso auxiliar no heredase la carpeta, no debe crear otra que nadie borraría."""
    monkeypatch.setattr(multiprocessing.current_process(), 'name', 'SpawnProcess-1')
    environ = {'LUMINA_DATA_DIR': str(data_dir)}
    Launcher(environ).prepare()
    assert 'NICEGUI_STORAGE_PATH' not in environ


def test_an_explicit_secret_is_respected(data_dir: Path, tmp_path: Path) -> None:
    environ = {
        'LUMINA_DATA_DIR': str(data_dir),
        'LUMINA_STORAGE_SECRET': 'clave-propia',
        'NICEGUI_STORAGE_PATH': str(tmp_path / 'sesiones'),
    }
    launcher = Launcher(environ)
    try:
        assert launcher.prepare().storage_secret == 'clave-propia'
    finally:
        launcher.release()


def test_browser_mode_keeps_the_configured_sessions(data_dir: Path) -> None:
    environ = {'LUMINA_DATA_DIR': str(data_dir), 'LUMINA_NATIVE': 'false'}
    launcher = Launcher(environ)
    try:
        assert launcher.prepare().storage_secret == DEVELOPMENT_SECRET
    finally:
        launcher.release()
    assert 'LUMINA_STORAGE_SECRET' not in environ
    assert 'NICEGUI_STORAGE_PATH' not in environ


def test_the_launcher_runs_before_nicegui_is_imported() -> None:
    """NiceGUI lee ``NICEGUI_STORAGE_PATH`` al importarse: el lanzador debe ejecutarse antes."""
    code = 'import sys, lumina.launcher; sys.exit("nicegui" in sys.modules)'
    result = subprocess.run(
        [sys.executable, '-c', code], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr or 'lumina.launcher importa NiceGUI'
