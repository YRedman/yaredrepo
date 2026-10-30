from ..ubicacion import describir_ubicacion, raiz_del_skill
from .base import Comando


class Donde(Comando):
    nombre = "donde"
    ayuda = "Muestra dónde está el skill fuente-corpus y cómo ejecutar corpus.py (no carga el corpus)."
    requiere_corpus = False

    def ejecutar(self, ctx, args):
        ctx.salida.lista(describir_ubicacion(raiz_del_skill()), prefijo="")
