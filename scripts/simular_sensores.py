"""Genera lecturas y escenarios del Sprint 3 mediante repositorios con escritura atómica y lectura estricta.

La aplicación ya simula por sí misma lecturas en vivo (:class:`lumina.controllers.LiveSimulator`);
mientras este script escribe un sensor (también con ``--escenario``), ella se lo deja y lo retoma dos
minutos después de su última escritura. Por defecto usa la carpeta de datos de la aplicación
(``datos-locales/``).

Uso: ``python scripts/simular_sensores.py --intervalo 3 --movimiento``.
Sin ``--movimiento`` se conservan las detecciones y sus horas originales.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lumina.controllers import Clock, SystemClock
from lumina.launcher import DataFolder
from lumina.models import Sensor, SensorStatus, SensorType, SystemConfig
from lumina.repositories import Repositories
from lumina.settings import SAMPLE_DATA_DIR, AppSettings


class SensorSimulator:
    """Variación ambiental y entradas/salidas virtuales acotadas por sensor."""

    def __init__(
        self,
        repositories: Repositories,
        clock: Clock,
        rng: random.Random,
        *,
        motion: bool = False,
    ) -> None:
        self._repositories = repositories
        self._clock = clock
        self._rng = rng
        self._motion = motion

    def step(self) -> list[Sensor]:
        """Modifica cada sensor a partir de su versión vigente dentro de ``modify``.

        No inventa lecturas ausentes ni repara estados de error/desactualizado. Cada lectura
        se guarda completa; no se sobrescriben cámaras ni campos de sensores concurrentes.
        """
        config = self._repositories.config.load()
        updated: list[Sensor] = []

        def change(current: Sensor) -> Sensor:
            value = self._next_value(current, config)
            if value is None:
                return current
            reading = replace(current, value=value, updated_at=self._clock.now())
            updated.append(reading)
            return reading

        for sensor in self._repositories.sensors.list_all():
            self._repositories.sensors.modify(sensor.id, change)
        return updated

    def scenario(self, name: str) -> list[Sensor]:
        """Escenario determinista de demostración; cada sensor se modifica de forma atómica.

        A diferencia de la variación aleatoria, restablece las lecturas utilizadas para
        poder repetir la demostración después del escenario de fallo.
        """
        config = self._repositories.config.load()
        if name not in ('calor', 'critica', 'movimiento', 'normal', 'fallo'):
            raise ValueError('Escenario desconocido.')
        updated: list[Sensor] = []

        def change(current: Sensor) -> Sensor:
            value = current.value
            status = SensorStatus.ACTIVE
            if current.type is SensorType.TEMPERATURE:
                if name == 'calor':
                    value = config.fan_threshold + 1
                elif name == 'critica':
                    value = config.critical_temperature
                elif name == 'normal':
                    value = config.fan_threshold - 1
                elif name == 'fallo':
                    status = SensorStatus.ERROR
                else:
                    return current
            elif current.type is SensorType.MOTION and current.zone_id == 'almacen':
                if name not in ('movimiento', 'normal'):
                    return current
                value = 1.0 if name == 'movimiento' else 0.0
            else:
                return current
            result = replace(current, value=value, status=status, updated_at=self._clock.now())
            updated.append(result)
            return result

        for sensor in self._repositories.sensors.list_all():
            self._repositories.sensors.modify(sensor.id, change)
        return updated

    def _next_value(self, sensor: Sensor, config: SystemConfig) -> float | None:
        current = sensor.value
        if current is None or not math.isfinite(current) or sensor.status is not SensorStatus.ACTIVE:
            return None
        match sensor.type:
            case SensorType.TEMPERATURE:
                return round(min(max(current + self._rng.uniform(-0.3, 0.3), 18.0), 33.0), 1)
            case SensorType.HUMIDITY:
                return round(min(max(current + self._rng.uniform(-1.0, 1.0), 0.0), 100.0), 1)
            case SensorType.PEOPLE_COUNTER:
                return float(min(max(round(current) + self._rng.randint(-6, 6), 0), config.max_occupancy))
            case SensorType.VEHICLE_COUNTER:
                return float(min(max(round(current) + self._rng.randint(-2, 2), 0), config.parking_spaces))
            case SensorType.MOTION:
                return float(self._rng.randint(0, 1)) if self._motion else None
            case SensorType.DISTANCE:
                return None


def main() -> None:
    """Interfaz de terminal; no importa ni arranca la aplicación gráfica."""
    parser = argparse.ArgumentParser(description='Simula temperatura, humedad, aforo, parking y movimiento opcional.')
    parser.add_argument('--datos', type=Path, default=AppSettings.from_env().data_dir, help='carpeta de datos JSON')
    parser.add_argument('--intervalo', type=float, default=3.0, help='segundos entre ciclos (mayor que 0)')
    parser.add_argument('--ciclos', type=int, default=0, help='número de ciclos; 0 = hasta Ctrl+C')
    parser.add_argument('--semilla', type=int, default=None, help='semilla para una simulación repetible')
    parser.add_argument('--movimiento', action='store_true', help='simular también las detecciones de movimiento')
    parser.add_argument(
        '--escenario', choices=('calor', 'critica', 'movimiento', 'normal', 'fallo'),
        help='escribe una vez el escenario y termina; la aplicación evalúa las reglas',
    )
    args = parser.parse_args()
    if not math.isfinite(args.intervalo) or args.intervalo <= 0 or args.ciclos < 0:
        parser.error('El intervalo debe ser positivo y finito; los ciclos deben ser mayores o iguales que cero.')
    DataFolder(args.datos).fill_from(SAMPLE_DATA_DIR)  # la misma carpeta de trabajo que usa la aplicación
    simulator = SensorSimulator(
        Repositories.from_json_dir(args.datos), SystemClock(), random.Random(args.semilla), motion=args.movimiento
    )
    if args.escenario:
        readings = simulator.scenario(args.escenario)
        print(f'Escenario {args.escenario}: {len(readings)} lecturas actualizadas.')
        return
    cycle = 0
    try:
        while args.ciclos == 0 or cycle < args.ciclos:
            cycle += 1
            readings = simulator.step()
            summary = ', '.join(f'{sensor.id}={sensor.value:g}' for sensor in readings if sensor.value is not None)
            print(f'[{cycle}] {summary}', flush=True)
            if args.ciclos == 0 or cycle < args.ciclos:
                time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print('\nSimulación detenida.')


if __name__ == '__main__':
    main()
