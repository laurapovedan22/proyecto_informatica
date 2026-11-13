"""Controladores: lógica de negocio entre el Modelo (repositorios) y la Vista (NiceGUI).

Ningún módulo de este paquete importa NiceGUI, de modo que la lógica puede probarse
y reutilizarse sin interfaz gráfica.
"""

from .analysis import FacilityAnalyzer
from .auth import AuthController
from .clock import Clock, FixedClock, SystemClock
from .errors import AuthenticationError, LuminaError, NotFoundError, PermissionDeniedError, ValidationError
from .facility import FacilityController
from .security import IdGenerator, PasswordHasher, UserInputValidator
from .services import Services
from .simulation import LiveSimulator
from .supervision import SupervisionController
from .users import NewUserCredentials, UserController

__all__ = [
    'AuthController',
    'AuthenticationError',
    'Clock',
    'FacilityAnalyzer',
    'FacilityController',
    'FixedClock',
    'IdGenerator',
    'LiveSimulator',
    'LuminaError',
    'NewUserCredentials',
    'NotFoundError',
    'PasswordHasher',
    'PermissionDeniedError',
    'Services',
    'SupervisionController',
    'SystemClock',
    'UserController',
    'UserInputValidator',
    'ValidationError',
]
