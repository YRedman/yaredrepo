"""``corpus.py llenar-k4``: escribe los datos de una entrevista en el K4 en blanco sin tocar la estructura del formulario."""

import json
from pathlib import Path

from ... import VERSION
from ...comun.errores import CorpusError
from ..vaciado.llenado_k4 import DatosInvalidos, estructura_de, llenar_k4
from ..vaciado.metodologia import VerificacionFallida
from ..vaciado.resumen import texto_llenado
from .base import Comando

LIMITE_ERRORES_MOSTRADOS = 15


def _datos(ruta):
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise CorpusError(f"No pude leer los datos «{ruta}»: {e}")
    if not isinstance(datos, dict):
        raise CorpusError("Los datos deben ser un objeto JSON: {\"colaborador\": {...}, \"general\": [{...}], \"actividades\": [...], …}. "
                          "Usa --estructura para ver las claves y los campos.")
    return datos


class LlenarK4(Comando):
    nombre = "llenar-k4"
    ayuda = "Escribe los datos de la entrevista en una copia del K4 en blanco sin cambiar su estructura (encabezados, formatos, listas)."
    requiere_corpus = False

    def configurar(self, parser):
        parser.add_argument("--base", required=True, help="Archivo .xlsx del K4 en blanco (el original del usuario; no se modifica).")
        parser.add_argument("--datos", default=None, help="JSON con colaborador, exposicion y una lista de registros por hoja.")
        parser.add_argument("--salida", default=None, help="Archivo .xlsx que se genera (por defecto «K4_completado.xlsx» junto a la base).")
        parser.add_argument("--estructura", action="store_true",
                            help="Solo muestra dónde se escribe en cada hoja de la base (claves, campos, valores permitidos y filas).")

    def ejecutar(self, ctx, args):
        s = ctx.salida
        if not Path(args.base).is_file():
            raise CorpusError(f"No encuentro el K4 base «{args.base}». Revisa /mnt/data o indica la ruta completa.")
        try:
            if args.estructura:
                s.linea(f"ESTRUCTURA DEL K4 · corpus.py v{VERSION}")
                s.lista(estructura_de(args.base), prefijo="")
                return
            if not args.datos:
                raise CorpusError("Falta --datos (o usa --estructura para ver cómo armarlos).")
            destino = Path(args.salida) if args.salida else Path(args.base).resolve().with_name("K4_completado.xlsx")
            if destino.resolve() == Path(args.base).resolve():
                raise CorpusError("La salida no puede ser el archivo base: se trabaja siempre sobre una copia.")
            resultado = llenar_k4(args.base, _datos(args.datos), destino)
        except DatosInvalidos as e:
            raise CorpusError("No se escribió el archivo: " + " | ".join(e.errores[:LIMITE_ERRORES_MOSTRADOS]), 2)
        except VerificacionFallida as e:
            raise CorpusError("La verificación falló y el archivo no se entregó (se borró): " + " | ".join(e.errores[:LIMITE_ERRORES_MOSTRADOS]), 2)
        s.linea(f"K4 LLENADO · corpus.py v{VERSION}")
        s.lista(texto_llenado(resultado, Path(args.base).name, Path(args.datos).name), prefijo="")
