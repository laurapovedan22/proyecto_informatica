"""Variables virtuales: información calculada por los controladores para las vistas.

En el Sprint 1 solo hay contadores de cuentas. Las variables del establecimiento (aforo,
ocupación del parking, estado de los sensores…) llegan en el Sprint 2.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserCounts:
    """Contadores del panel de administración."""

    total: int
    connected: int
    pending: int
    inactive: int = 0
