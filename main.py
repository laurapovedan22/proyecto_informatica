"""Punto de entrada de Lumina: ``python main.py`` o el ejecutable creado con ``scripts/empaquetar.py``.

Lumina se abre en una ventana de escritorio propia. La configuración se puede ajustar con
variables de entorno ``LUMINA_*`` (ver README).
"""

from multiprocessing import freeze_support

from lumina.launcher import Launcher

# NiceGUI ejecuta este fichero también como «__mp_main__» en sus procesos auxiliares (la ventana
# y la recarga en caliente); allí ``ui.run`` registra las páginas sin arrancar otro servidor.
if __name__ in {'__main__', '__mp_main__'}:
    # En el ejecutable, NiceGUI abre la ventana relanzando el propio programa: freeze_support()
    # reconoce ese proceso, ejecuta solo su tarea y termina antes de llegar a la aplicación.
    Launcher.prepare_auxiliary_process()  # antes, para que sus errores queden registrados
    freeze_support()
    Launcher().run()
