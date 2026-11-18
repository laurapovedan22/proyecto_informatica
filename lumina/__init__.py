"""Lumina: plataforma de supervisión IoT para un supermercado y su parking (entrega del Sprint 3).

El paquete sigue el patrón Modelo-Vista-Controlador descrito en el anteproyecto:

- ``lumina.models``: entidades del dominio y variables virtuales (sin dependencias de E/S).
- ``lumina.repositories``: acceso a datos. En la fase 1 se usan ficheros JSON.
- ``lumina.controllers``: acceso, usuarios, supervisión, configuración y reglas automáticas del Sprint 3,
  y el análisis de imagen con YOLO (personas en zonas restringidas).
- ``lumina.views``: interfaz gráfica construida únicamente con la API Python de NiceGUI.
"""

__version__ = '0.1.0'
