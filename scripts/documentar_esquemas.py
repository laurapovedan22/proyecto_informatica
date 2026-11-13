"""Regenera las tablas de ``docs/esquemas-json.md`` desde JSON Schema, sin dependencias externas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, ClassVar, TypeAlias

Schema: TypeAlias = dict[str, Any]
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SchemaDocumenter:
    """Documenta propiedades, definiciones, tipos, obligatoriedad y límites del contrato JSON."""

    FILES: ClassVar[tuple[tuple[str, str, str], ...]] = (
        ('usuarios', 'Cuentas, perfiles y solicitudes', '**Sprint 1** (H1.2–H1.4)'),
        ('sensores', 'Última lectura de cada sensor y cámaras', 'Sprint 2 (H2.1–H2.4)'),
        ('actuadores', 'Estado de ventiladores, LED y alarma', 'Sprint 3 (H3.2, H3.3)'),
        ('alertas', 'Alertas e incidencias', 'Sprint 3 (H3.2, H3.4)'),
        ('historicos', 'Serie histórica de lecturas', 'Sprint 4 (H4.1)'),
        ('configuracion', 'Aforo, plazas, umbrales y zonas', 'Sprint 2 (consulta); Sprint 3 (H3.1, edición)'),
    )
    TYPES: ClassVar[dict[str, str]] = {
        'string': 'texto',
        'integer': 'entero',
        'number': 'número',
        'boolean': 'booleano',
        'null': 'null',
        'object': 'objeto',
    }
    INTRO = """# Esquemas de los ficheros JSON

Contrato de datos de Lumina (H1.1). Cada fichero de `data/` tiene un esquema formal en
`schemas/` (JSON Schema 2020-12) que **es la referencia**: este documento se genera a partir de
ellos y los tests (`tests/test_schemas.py`) comprueban que los datos de ejemplo y lo que escribe
la aplicación los cumplen.

- Las claves están en español porque son el contrato compartido con la parte IoT.
- Las fechas van en ISO 8601 y hora local (`2026-10-14T14:30:00`); con zona horaria se convierten.
- Un fichero se escribe siempre completo y de una vez (fichero temporal + renombrado), nunca a medias.
- Los identificadores (`id`) son únicos dentro de cada lista y las zonas se referencian por su `id`
  de `configuracion.json`.
"""

    def __init__(self, schemas_dir: Path) -> None:
        self._schemas_dir = schemas_dir

    def render(self) -> str:
        """Genera el documento completo en orden estable; incluye también esquemas nuevos."""
        available = {path.stem.removesuffix('.schema'): path for path in self._schemas_dir.glob('*.schema.json')}
        order = [name for name, _, _ in self.FILES if name in available]
        order.extend(sorted(available.keys() - set(order)))
        schemas: dict[str, Schema] = {name: json.loads(available[name].read_text(encoding='utf-8')) for name in order}
        metadata = {name: (content, sprint) for name, content, sprint in self.FILES}
        lines = [
            self.INTRO.rstrip(),
            '',
            '| Fichero | Contenido | Se usa a partir de |',
            '| ------- | --------- | ------------------ |',
        ]
        for name in order:
            content, sprint = metadata.get(name, (schemas[name].get('description', ''), 'Por determinar'))
            lines.append(f'| `{name}.json` | {content} | {sprint} |')
        for name, schema in schemas.items():
            lines.extend(['', f'## `{name}.json`', '', schema.get('description', ''), ''])
            lines.extend(self._table(schema))
            for definition, item in schema.get('$defs', {}).items():
                lines.extend(['', f'**{definition}** · {item.get("description", "")}', ''])
                lines.extend(self._table(item))
        lines.extend(['', '---', '', '_Generado a partir de `schemas/`. Si cambia un esquema, hay que regenerarlo._'])
        return '\n'.join(lines) + '\n'

    @classmethod
    def _table(cls, schema: Schema) -> list[str]:
        lines = ['| Campo | Tipo | Oblig. | Descripción |', '| ----- | ---- | :----: | ----------- |']
        for name, field in schema.get('properties', {}).items():
            required = '✓' if name in schema.get('required', []) else ''
            description = field.get('description', '')
            constraints: list[str] = []
            if 'default' in field:
                default = field['default']
                value = json.dumps(default, ensure_ascii=False) if not isinstance(default, str) else default
                constraints.append(f'por defecto `{value}`')
            if 'maxLength' in field:
                constraints.append(f'máx. {field["maxLength"]} caracteres')
            if 'minimum' in field:
                constraints.append(f'≥ {field["minimum"]}')
            if constraints:
                description += f' ({"; ".join(constraints)})'
            description = description.replace('|', '\\|').replace('\n', ' ')
            lines.append(f'| `{name}` | {cls._type(field)} | {required} | {description} |')
        return lines

    @classmethod
    def _type(cls, field: Schema) -> str:
        if 'enum' in field:
            return ' · '.join('null' if value is None else f'`{value}`' for value in field['enum'])
        if '$ref' in field:
            return f'*{field["$ref"].rsplit("/", 1)[-1]}*'
        kind = field.get('type', 'object')
        if isinstance(kind, list):
            return ' · '.join(cls._type({**field, 'type': member}) for member in kind)
        if kind == 'array':
            return f'lista de {cls._type(field.get("items", {}))}'
        if kind == 'string' and ('ISO 8601' in field.get('description', '') or field.get('format') == 'date-time'):
            return 'fecha ISO 8601'
        return cls.TYPES.get(kind, kind) if isinstance(kind, str) else 'objeto'


def main() -> None:
    """Permite regenerar el documento desde cualquier carpeta de trabajo."""
    parser = argparse.ArgumentParser(description='Documenta los esquemas JSON de Lumina.')
    parser.add_argument('--esquemas', type=Path, default=PROJECT_ROOT / 'schemas')
    parser.add_argument('--salida', type=Path, default=PROJECT_ROOT / 'docs' / 'esquemas-json.md')
    args = parser.parse_args()
    args.salida.write_text(SchemaDocumenter(args.esquemas).render(), encoding='utf-8')


if __name__ == '__main__':
    main()
