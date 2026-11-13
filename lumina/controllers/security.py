"""Contraseñas, identificadores y validación de datos de usuario."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from .errors import ValidationError


class PasswordHasher:
    """Hash de contraseñas con PBKDF2-SHA256 (solo biblioteca estándar).

    Formato guardado: ``pbkdf2_sha256$<iteraciones>$<sal hex>$<hash hex>``.
    """

    ALGORITHM = 'pbkdf2_sha256'

    def __init__(self, iterations: int = 200_000) -> None:
        self._iterations = iterations

    def hash(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = self._digest(password, salt, self._iterations)
        return f'{self.ALGORITHM}${self._iterations}${salt}${digest}'

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt, digest = encoded.split('$')
            rounds = int(iterations)
            if algorithm != self.ALGORITHM:
                return False
            return hmac.compare_digest(self._digest(password, salt, rounds), digest)
        except (ValueError, OverflowError, TypeError):
            # Un hash dañado se rechaza como credencial inválida, sin romper el formulario.
            return False

    @staticmethod
    def temporary_password() -> str:
        """Contraseña aleatoria para las cuentas que crea el administrador."""
        return secrets.token_urlsafe(9)

    @staticmethod
    def _digest(password: str, salt: str, iterations: int) -> str:
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), iterations).hex()


class IdGenerator:
    """Genera identificadores legibles y únicos (``usr-1a2b3c4d``)."""

    @staticmethod
    def new(prefix: str) -> str:
        return f'{prefix}-{secrets.token_hex(4)}'


class UserInputValidator:
    """Normaliza y valida los datos de usuario introducidos en formularios."""

    NAME_MAX_LENGTH = 45
    PASSWORD_MIN_LENGTH = 6
    _EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

    @classmethod
    def name(cls, value: str) -> str:
        cleaned = ' '.join(value.split())
        if not cleaned:
            raise ValidationError('El nombre es obligatorio.')
        if len(cleaned) > cls.NAME_MAX_LENGTH:
            raise ValidationError(f'El nombre no puede superar los {cls.NAME_MAX_LENGTH} caracteres.')
        return cleaned

    @classmethod
    def email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cls._EMAIL_PATTERN.match(cleaned):
            raise ValidationError('Introduce un correo electrónico válido.')
        return cleaned

    @classmethod
    def new_password(cls, password: str, confirmation: str) -> str:
        if len(password) < cls.PASSWORD_MIN_LENGTH:
            raise ValidationError(f'La contraseña debe tener al menos {cls.PASSWORD_MIN_LENGTH} caracteres.')
        if password != confirmation:
            raise ValidationError('Las contraseñas no coinciden.')
        return password
