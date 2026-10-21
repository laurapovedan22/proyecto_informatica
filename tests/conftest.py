"""Fixtures comunes: cada test trabaja sobre una copia de ``data/`` para no tocar los datos reales."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from lumina.controllers import FixedClock, PasswordHasher, Services
from lumina.models import User
from lumina.repositories import Repositories

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA = PROJECT_ROOT / 'data'
DEMO_NOW = datetime(2026, 10, 14, 14, 30)
"""Momento de los datos de ejemplo (mismo instante que el mockup)."""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    target = tmp_path / 'data'
    shutil.copytree(SAMPLE_DATA, target)
    return target


@pytest.fixture(autouse=True)
def lumina_environment(monkeypatch: pytest.MonkeyPatch, data_dir: Path, tmp_path: Path) -> None:
    """Configuración que lee ``main.py`` cuando lo ejecuta el fixture ``user`` de NiceGUI.

    Se usa la configuración por defecto (ventana de escritorio); la clave y la carpeta de las
    sesiones se fijan para que el lanzador no cree carpetas temporales ni cambie el entorno.
    """
    monkeypatch.setenv('LUMINA_DATA_DIR', str(data_dir))
    monkeypatch.setenv('LUMINA_REFRESH_SECONDS', '0')
    monkeypatch.setenv('LUMINA_RELOAD', 'false')
    monkeypatch.setenv('LUMINA_OPEN_BROWSER', 'false')
    monkeypatch.setenv('LUMINA_STORAGE_SECRET', 'secreto-de-pruebas')
    monkeypatch.setenv('NICEGUI_STORAGE_PATH', str(tmp_path / 'sesiones'))


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(DEMO_NOW)


@pytest.fixture
def repositories(data_dir: Path) -> Repositories:
    return Repositories.from_json_dir(data_dir)


@pytest.fixture
def services(repositories: Repositories, clock: FixedClock) -> Services:
    # Pocas iteraciones para que los tests sean rápidos (los hashes de ejemplo guardan las suyas).
    return Services.create(repositories, clock=clock, hasher=PasswordHasher(iterations=1_000))


def get_user(repositories: Repositories, user_id: str) -> User:
    user = repositories.users.get(user_id)
    assert user is not None, f'No existe el usuario de ejemplo {user_id}'
    return user


@pytest.fixture
def admin(repositories: Repositories) -> User:
    return get_user(repositories, 'usr-ana')


@pytest.fixture
def security(repositories: Repositories) -> User:
    return get_user(repositories, 'usr-carlos')


@pytest.fixture
def manager(repositories: Repositories) -> User:
    return get_user(repositories, 'usr-marta')
