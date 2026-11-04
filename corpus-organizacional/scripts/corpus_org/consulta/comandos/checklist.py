"""``corpus.py checklist``: ¿el K4 presentado trae lo necesario para pasarse a la plantilla metodologica?"""

from pathlib import Path

from ... import VERSION
from ...comun.errores import CorpusError
from ..vaciado.checklist import evaluar
from ..vaciado.k4 import leer_k4
from ..vaciado.resumen import texto_checklist
from .base import Comando


class Checklist(Comando):
    nombre = "checklist"
    ayuda = "Checklist de completitud (Sí/Parcial/No/N/A), carga laboral y calidad (1–5) de uno o más K4 antes de pasarlos a la plantilla."
    requiere_corpus = False

    def configurar(self, parser):
        parser.add_argument("--k4", nargs="+", required=True, help="Uno o más archivos .xlsx de K4 completados.")

    def ejecutar(self, ctx, args):
        s = ctx.salida
        resultados = []
        for ruta in args.k4:
            if not Path(ruta).is_file():
                raise CorpusError(f"No encuentro el K4 «{ruta}». Revisa /mnt/data o indica la ruta completa.")
            resultados.append(evaluar(leer_k4(ruta), Path(ruta).name))
        s.linea(f"CHECKLIST DE COMPLETITUD · corpus.py v{VERSION}")
        s.lista(texto_checklist(resultados), prefijo="")
