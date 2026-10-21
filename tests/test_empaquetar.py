"""Script de empaquetado: comando de PyInstaller y publicación en ``dist/`` (sin ejecutar PyInstaller)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location('empaquetar', PROJECT_ROOT / 'scripts' / 'empaquetar.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


empaquetar = load_script()


@pytest.fixture
def packager(tmp_path: Path) -> Any:
    return empaquetar.Packager(tmp_path / 'proyecto', tmp_path / 'trabajo', onefile=False, clean=False)


def build(packager: Any, folder: Path, version: str) -> Path:
    """Simula una versión de la aplicación (la carpeta ``Lumina.app`` o ``Lumina``) en ``folder``."""
    artifact: Path = packager.artifact(folder)
    artifact.mkdir(parents=True)
    (artifact / 'version.txt').write_text(version, encoding='utf-8')
    return artifact


def test_the_command_bundles_the_resources_but_not_the_development_tools(tmp_path: Path) -> None:
    packager = empaquetar.Packager(PROJECT_ROOT, tmp_path, onefile=False, clean=False)
    command: list[str] = packager.command(tmp_path / 'icono.png', tmp_path / 'datos')
    assert {'--windowed', '--noconfirm'} <= set(command)
    added = [command[index + 1] for index, item in enumerate(command) if item == '--add-data']
    assert f'{tmp_path / "datos"}{os.pathsep}data' in added
    assert f'{PROJECT_ROOT / "assets"}{os.pathsep}assets' in added
    assert any(item.endswith(f'{os.pathsep}nicegui') for item in added)
    excluded = {command[index + 1] for index, item in enumerate(command) if item == '--exclude-module'}
    assert {'mypy', 'PIL', 'pytest'} <= excluded


def test_publishing_replaces_the_previous_version(packager: Any, tmp_path: Path) -> None:
    build(packager, tmp_path / 'trabajo' / 'dist', 'nueva')
    build(packager, tmp_path / 'proyecto' / 'dist', 'anterior')
    published: Path = packager._publish()
    assert (published / 'version.txt').read_text(encoding='utf-8') == 'nueva'
    assert [path.name for path in published.parent.iterdir()] == [published.name]  # sin restos provisionales


def test_a_failed_publication_keeps_the_previous_version(
    packager: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(packager, tmp_path / 'trabajo' / 'dist', 'nueva')
    previous = build(packager, tmp_path / 'proyecto' / 'dist', 'anterior')
    real_replace = os.replace

    def replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        if Path(source).name == previous.name and Path(source).parent.name.startswith('.publicando-'):
            raise OSError('disco lleno')  # falla al colocar la versión nueva
        real_replace(source, target)

    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(OSError, match='disco lleno'):
        packager._publish()
    assert (previous / 'version.txt').read_text(encoding='utf-8') == 'anterior'
    assert [path.name for path in previous.parent.iterdir()] == [previous.name]


def test_if_even_the_rollback_fails_the_previous_version_is_kept_aside(
    packager: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(packager, tmp_path / 'trabajo' / 'dist', 'nueva')
    previous = build(packager, tmp_path / 'proyecto' / 'dist', 'anterior')
    real_replace = os.replace

    def replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        if Path(source).parent.name.startswith('.publicando-'):
            raise OSError('disco lleno')  # falla al colocar la versión nueva y al restaurar la anterior
        real_replace(source, target)

    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(OSError, match='disco lleno'):
        packager._publish()
    kept = next(previous.parent.glob('.publicando-*')) / 'anterior'
    assert (kept / 'version.txt').read_text(encoding='utf-8') == 'anterior'
    assert str(kept) in capsys.readouterr().err
