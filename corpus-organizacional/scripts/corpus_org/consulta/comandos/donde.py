from ..ubicacion import describir_ubicacion, raiz_del_skill
from .base import Comando


class Donde(Comando):
    nombre = "donde"
    ayuda = "Muestra dónde están fuente-contexto y fuente-documentos y cómo ejecutar corpus.py (no carga el corpus)."

    def ejecutar(self, ctx, args, salida=None):
        (salida or ctx.salida).lista(describir_ubicacion(raiz_del_skill()), prefijo="")
