"""La documentación del contrato se regenera desde los esquemas y se entrega al día."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.documentar_esquemas import SchemaDocumenter

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_schema_documentation_is_up_to_date() -> None:
    assert SchemaDocumenter(PROJECT_ROOT / 'schemas').render() == (
        PROJECT_ROOT / 'docs' / 'esquemas-json.md'
    ).read_text(encoding='utf-8')


def test_documenter_reads_schema_changes_and_new_files(tmp_path: Path) -> None:
    target = tmp_path / 'schemas'
    shutil.copytree(PROJECT_ROOT / 'schemas', target)
    path = target / 'sensores.schema.json'
    schema = json.loads(path.read_text(encoding='utf-8'))
    schema['$defs']['sensor']['properties']['nombre']['description'] = 'Descripción actualizada.'
    schema['$defs']['sensor']['required'].append('estado')
    path.write_text(json.dumps(schema), encoding='utf-8')
    (target / 'nuevo.schema.json').write_text(
        json.dumps(
            {
                'description': 'Contrato nuevo.',
                'type': 'object',
                'properties': {
                    'lectura': {'type': 'number', 'description': 'Lectura nueva.', 'minimum': 0, 'default': 1},
                },
            }
        ),
        encoding='utf-8',
    )
    output = tmp_path / 'esquemas.md'
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / 'scripts' / 'documentar_esquemas.py'),
            '--esquemas',
            str(target),
            '--salida',
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = output.read_text(encoding='utf-8')
    assert 'Descripción actualizada.' in rendered
    assert '| `estado` | `activo` · `error` · `desactualizado` | ✓ |' in rendered
    assert '## `nuevo.json`' in rendered
    assert '| `lectura` | número |  | Lectura nueva. (por defecto `1`; ≥ 0) |' in rendered
