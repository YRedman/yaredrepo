import json
from pathlib import Path

from ... import VERSION
from ...comun.errores import CorpusError
from ..ubicacion import raiz_del_skill
from ..vaciado.k4 import leer_k4
from ..vaciado.metodologia import VerificacionFallida, vaciar_k4
from ..vaciado.resumen import texto_k4, texto_resultado
from .base import Comando

CARPETA_FORMULARIOS = "formularios"
PALABRAS_DE_PLANTILLA = ("plantilla", "metodolog")
LIMITE_ERRORES_MOSTRADOS = 15


def _localizar_plantilla(explicita, k4):
    """La plantilla indicada o, si no, la del skill (formularios/) o una junto al K4."""
    if explicita:
        if not Path(explicita).is_file():
            raise CorpusError(f"No encuentro la plantilla «{explicita}».")
        return Path(explicita)
    for carpeta in (raiz_del_skill() / CARPETA_FORMULARIOS, Path(k4).resolve().parent, Path("/mnt/data")):
        if carpeta.is_dir():
            for p in sorted(carpeta.glob("*.xlsx")):
                if all(w in p.name.lower() for w in ("pwc",)) or any(w in p.name.lower() for w in PALABRAS_DE_PLANTILLA):
                    return p
    raise CorpusError("No encuentro la plantilla metodológica (.xlsx). Indícala con --plantilla.")


def _complementos(ruta):
    if not ruta:
        return {}
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise CorpusError(f"No pude leer los complementos «{ruta}»: {e}")
    if not isinstance(datos, dict):
        raise CorpusError("Los complementos deben ser un objeto JSON con las claves campos, actividades_nuevas, puntos o evidencias.")
    return datos


class Vaciar(Comando):
    nombre = "vaciar"
    ayuda = "Pasa un K4 (formulario del puesto) a la plantilla metodológica de carga laboral, con su hoja de puntos a validar."
    requiere_corpus = False

    def configurar(self, parser):
        parser.add_argument("--k4", required=True, help="Archivo .xlsx del K4 completado.")
        parser.add_argument("--plantilla", default=None, help="Plantilla metodológica .xlsx (por defecto la de formularios/).")
        parser.add_argument("--salida", default=None, help="Archivo .xlsx que se genera (por defecto junto al K4).")
        parser.add_argument("--complementos", default=None,
                            help="JSON con lo que aportan la transcripción y la minuta (campos, actividades_nuevas, puntos, evidencias).")
        parser.add_argument("--fuentes", nargs="*", default=[], help="Nombres de la transcripción y la minuta, para la hoja Evidencias.")
        parser.add_argument("--leer", action="store_true", help="Solo muestra lo que se lee del K4; no genera el archivo.")

    def ejecutar(self, ctx, args):
        s = ctx.salida
        if not Path(args.k4).is_file():
            raise CorpusError(f"No encuentro el K4 «{args.k4}». Revisa /mnt/data o indica la ruta completa.")
        if args.leer:
            s.linea(f"K4 · corpus.py v{VERSION}")
            s.lista(texto_k4(leer_k4(args.k4)), prefijo="")
            return
        plantilla = _localizar_plantilla(args.plantilla, args.k4)
        destino = Path(args.salida) if args.salida else Path(args.k4).resolve().with_name(f"Metodologia_{Path(args.k4).stem}.xlsx")
        if destino.resolve() in (Path(args.k4).resolve(), plantilla.resolve()):
            raise CorpusError("La salida no puede ser el K4 ni la plantilla.")
        try:
            resultado, k4, celdas = vaciar_k4(args.k4, plantilla, destino, _complementos(args.complementos), args.fuentes)
        except VerificacionFallida as e:
            raise CorpusError("La verificación falló y el archivo no se entregó (se borró): "
                              + " | ".join(e.errores[:LIMITE_ERRORES_MOSTRADOS]), 2)
        s.linea(f"VACIADO · corpus.py v{VERSION}")
        s.lista(texto_resultado(resultado, k4, Path(args.k4).name, plantilla.name, celdas), prefijo="")
