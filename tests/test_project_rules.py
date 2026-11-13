"""Reglas del proyecto: la interfaz se escribe solo en Python (sin JavaScript, Vue ni CSS a mano)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = (PROJECT_ROOT / 'lumina', PROJECT_ROOT / 'scripts')
PYTHON_FILES = sorted(path for directory in SOURCE_DIRS for path in directory.rglob('*.py'))

FORBIDDEN = {
    'ui.run_javascript': 'ejecuta JavaScript en el navegador',
    'run_method(': 'llama a métodos JavaScript de un componente',
    'js_handler': 'manejador de eventos en JavaScript',
    'add_body_html': 'inyecta HTML/JavaScript en la página',
    'add_head_html': 'inyecta HTML/JavaScript en la cabecera',
    'add_css': 'CSS escrito a mano (usar clases Tailwind desde theme.py)',
    'add_scss': 'SCSS escrito a mano',
    'add_sass': 'Sass escrito a mano',
    'ui.html(': 'HTML sin procesar',
    'component=': 'componente Vue/JavaScript propio',
    '<script': 'etiqueta script',
}
JS_EXPRESSION_PROP = re.compile(r"""\.props\(\s*['"][^'"]*(^|\s):[\w-]+=""")


@pytest.mark.parametrize('path', PYTHON_FILES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_no_javascript_vue_or_css(path: Path) -> None:
    source = path.read_text(encoding='utf-8')
    for pattern, reason in FORBIDDEN.items():
        assert pattern not in source, f'{path.name} usa «{pattern}»: {reason}'
    assert not JS_EXPRESSION_PROP.search(source), f'{path.name} usa props con expresiones JavaScript («:prop=»)'


def test_no_frontend_files() -> None:
    frontend = [path for directory in SOURCE_DIRS for suffix in ('*.js', '*.vue', '*.css', '*.scss')
                for path in directory.rglob(suffix)]
    assert not frontend, f'Ficheros de frontend no permitidos: {frontend}'
