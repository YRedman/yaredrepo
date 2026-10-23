"""Registro de modos de ``convertir.py`` (en el orden en que se muestran en la ayuda)."""

from .construir import Construir
from .contexto import Contexto
from .convertir import Convertir
from .inventariar import Inventariar
from .utilidades import Diagnostico, Informe, Matriz

MODOS = {m.nombre: m for m in (Inventariar(), Convertir(), Contexto(), Construir(), Informe(), Diagnostico(), Matriz())}
