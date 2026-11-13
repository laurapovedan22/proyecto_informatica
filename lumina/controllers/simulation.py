"""Lecturas «en vivo»: la aplicación simula continuamente la maqueta IoT mientras no haya otra fuente.

:class:`LiveSimulator` escribe en ``sensores.json`` mediante los repositorios, exactamente como lo
haría la maqueta física, de modo que análisis y vistas no cambian: la interfaz sigue releyendo el
JSON y, como los datos cambian en cada ciclo, nunca muestra siempre el mismo valor.
:class:`lumina.app.LuminaApp` lo ejecuta en segundo plano; este módulo no importa NiceGUI.
"""

from __future__ import annotations

import math
import random
import threading
from dataclasses import replace
from datetime import datetime, timedelta
from typing import ClassVar

from ..models import Sensor, SensorStatus, SensorType, SystemConfig
from ..repositories import Repositories
from .clock import Clock


class LiveSimulator:
    """Genera lecturas continuas y verosímiles para todos los sensores operativos.

    - **Temperatura y humedad** oscilan poco a poco alrededor de su valor habitual, con un ciclo
      diario suave (más calor y menos humedad por la tarde).
    - **Aforo y parking** siguen la afluencia típica de cada hora (picos a mediodía y por la tarde),
      con entradas y salidas en cada ciclo, siempre entre cero y la capacidad configurada.
    - **Distancia** del acceso al parking: mide el fondo y baja cuando pasa un coche.
    - **Movimiento**: detecciones breves y esporádicas en cada zona.
    - Todas las lecturas operativas renuevan su hora en cada ciclo, como un sensor que informa.

    Nunca inventa lecturas que faltan ni repara sensores en error o desactualizados. Si otra fuente
    escribe un sensor (la maqueta IoT, ``scripts/simular_sensores.py`` o sus escenarios), el
    simulador se lo deja durante :attr:`EXTERNAL_HOLD` desde su última escritura.
    """

    EXTERNAL_HOLD: ClassVar[timedelta] = timedelta(minutes=2)
    """Tiempo sin escrituras ajenas que espera antes de volver a simular un sensor."""
    MOTION_GAP_SECONDS: ClassVar[float] = 300.0
    """Tiempo medio entre dos detecciones de un mismo sensor de movimiento."""
    CAR_GAP_SECONDS: ClassVar[float] = 40.0
    """Tiempo medio entre dos coches que pasan ante el sensor de distancia del acceso."""

    def __init__(self, repositories: Repositories, clock: Clock, *, rng: random.Random | None = None) -> None:
        self._repositories = repositories
        self._clock = clock
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._step_seconds = 5.0
        self._written: dict[str, Sensor] = {}
        """Última lectura que ha guardado el simulador de cada sensor (para notar escrituras ajenas)."""
        self._held_until: dict[str, datetime] = {}
        self._baselines: dict[str, float] = {}
        self._motion_until: dict[str, datetime] = {}

    def step(self, seconds: float = 5.0) -> list[Sensor]:
        """Escribe un ciclo que representa ``seconds`` segundos y devuelve las lecturas guardadas.

        Cada sensor se modifica por separado mediante ``modify``, a partir de su versión vigente.
        """
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('La duración del ciclo debe ser positiva.')
        with self._lock:
            self._step_seconds = seconds
            config = self._repositories.config.load()
            now = self._clock.now()
            saved: list[Sensor] = []
            for sensor in self._repositories.sensors.list_all():
                saved.extend(self._simulate(sensor.id, config, now))
            return saved

    def _simulate(self, sensor_id: str, config: SystemConfig, now: datetime) -> list[Sensor]:
        produced: list[Sensor] = []

        def change(current: Sensor) -> Sensor:
            if self._held(current, now):
                return current
            value = self._next_value(current, config, now)
            if value is None:
                return current
            produced.append(replace(current, value=value, updated_at=now))
            return produced[0]

        self._repositories.sensors.modify(sensor_id, change)
        if produced:  # guardado: modify no ha lanzado ninguna excepción
            self._written[sensor_id] = produced[0]
        return produced

    def _held(self, current: Sensor, now: datetime) -> bool:
        """``True`` mientras otra fuente controla el sensor (lo escribió hace menos de :attr:`EXTERNAL_HOLD`)."""
        written = self._written.get(current.id)
        if written is not None and current != written:
            self._held_until[current.id] = now + self.EXTERNAL_HOLD
            self._written[current.id] = current
        until = self._held_until.get(current.id)
        if until is None:
            return False
        if now < until:
            return True
        del self._held_until[current.id]
        return False

    def _next_value(self, sensor: Sensor, config: SystemConfig, now: datetime) -> float | None:
        current = sensor.value
        if current is None or not math.isfinite(current) or sensor.status is not SensorStatus.ACTIVE:
            return None
        hour = now.hour + now.minute / 60
        day_cycle = math.sin(2 * math.pi * (hour - 9) / 24)  # máximo a las 15:00 y mínimo a las 3:00
        match sensor.type:
            case SensorType.TEMPERATURE:
                target = self._baseline(sensor.id, current, low=16.0, high=25.0) + 0.5 * day_cycle
                return round(self._drift(current, target, tau=180.0, sigma=0.03), 1)
            case SensorType.HUMIDITY:
                target = self._baseline(sensor.id, current, low=35.0, high=65.0) - 3.0 * day_cycle
                return round(min(max(self._drift(current, target, tau=240.0, sigma=0.1), 0.0), 100.0), 1)
            case SensorType.PEOPLE_COUNTER:
                expected = config.max_occupancy * self.store_crowd(hour)
                return self._count(current, expected, config.max_occupancy, tau=300.0, sigma=1.0)
            case SensorType.VEHICLE_COUNTER:
                expected = config.parking_spaces * self.parking_crowd(hour)
                return self._count(current, expected, config.parking_spaces, tau=420.0, sigma=0.4)
            case SensorType.DISTANCE:
                return self._distance(sensor.id, current)
            case SensorType.MOTION:
                return self._motion(sensor.id, current, now)

    # --- Modelos de cada tipo de sensor ---------------------------------------------------------

    @staticmethod
    def store_crowd(hour: float) -> float:
        """Fracción del aforo esperada a una hora: picos hacia las 13:00 y las 19:30."""
        return 0.22 + 0.36 * math.exp(-(((hour - 13.0) / 1.8) ** 2)) + 0.46 * math.exp(-(((hour - 19.5) / 2.0) ** 2))

    @staticmethod
    def parking_crowd(hour: float) -> float:
        """Fracción de plazas ocupadas esperada a una hora: picos hacia las 12:30 y las 19:00."""
        return 0.25 + 0.35 * math.exp(-(((hour - 12.5) / 2.0) ** 2)) + 0.40 * math.exp(-(((hour - 19.0) / 2.2) ** 2))

    def _baseline(self, sensor_id: str, value: float, *, low: float, high: float) -> float:
        """Valor habitual del sensor: el primero que ve el simulador, dentro de un margen razonable."""
        return self._baselines.setdefault(sensor_id, min(max(value, low), high))

    def _drift(self, value: float, target: float, *, tau: float, sigma: float) -> float:
        """Paso de un paseo aleatorio que tiende a ``target`` (proceso de Ornstein-Uhlenbeck).

        ``tau`` es el tiempo característico de vuelta, en segundos, y ``sigma`` la agitación por
        raíz de segundo; así el comportamiento no depende de la duración del ciclo.
        """
        pull = 1 - math.exp(-self._step_seconds / tau)
        return value + (target - value) * pull + self._rng.gauss(0.0, sigma * math.sqrt(self._step_seconds))

    def _count(self, value: float, expected: float, capacity: int, *, tau: float, sigma: float) -> float:
        """Entradas y salidas del ciclo: tiende a la afluencia esperada sin salir de [0, capacidad]."""
        moved = round(self._drift(value, expected, tau=tau, sigma=sigma))
        return float(min(max(moved, 0), max(capacity, 0)))

    def _chance(self, mean_gap_seconds: float) -> bool:
        """Si ocurre en este ciclo un suceso que pasa, de media, cada ``mean_gap_seconds``."""
        return self._rng.random() < 1 - math.exp(-self._step_seconds / mean_gap_seconds)

    def _distance(self, sensor_id: str, value: float) -> float:
        """Ultrasonidos del acceso: sin coche mide el fondo (unos 180 cm); al pasar uno, mucho menos."""
        background = self._baseline(sensor_id, value, low=120.0, high=400.0)
        if self._chance(self.CAR_GAP_SECONDS):
            return float(round(self._rng.uniform(35.0, 95.0)))
        return float(round(self._rng.gauss(background, 2.0)))

    def _motion(self, sensor_id: str, value: float, now: datetime) -> float:
        """Detecciones de 15 a 45 segundos; una que ya estuviera en curso termina en unos segundos."""
        until = self._motion_until.get(sensor_id)
        if until is None and value > 0:
            until = self._motion_until[sensor_id] = now + timedelta(seconds=self._rng.uniform(10.0, 40.0))
        if until is not None:
            if now < until:
                return 1.0
            del self._motion_until[sensor_id]
            return 0.0
        if self._chance(self.MOTION_GAP_SECONDS):
            self._motion_until[sensor_id] = now + timedelta(seconds=self._rng.uniform(15.0, 45.0))
            return 1.0
        return 0.0
