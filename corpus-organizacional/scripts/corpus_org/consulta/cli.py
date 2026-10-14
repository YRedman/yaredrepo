"""Linea de comandos de ``corpus.py``."""

import argparse
import sys
from pathlib import Path

from ..comun.errores import AreaAmbigua, AreaNoEncontrada, CorpusError
from .comandos import COMANDOS
from .comandos.base import Contexto
from .repositorio import cargar_corpus
from .salida import Salida
from .ubicacion import incluir_no_vigentes, resolver_ubicacion

def _raiz_skill():
    """Carpeta que contiene scripts/: el skill fuente-contexto (o el repositorio)."""
    for p in Path(__file__).resolve().parents:
        if p.name == "scripts":
            return p.parent
    return Path(__file__).resolve().parents[3]


RAIZ_SKILL = _raiz_skill()


class _Parser(argparse.ArgumentParser):
    """argparse que informa los errores con el mismo formato que el resto del script."""

    def error(self, message):
        raise CorpusError(f"{message}. Ejemplo: python scripts/corpus.py {self.prog.split()[-1]} \"Seguridad\"")


def crear_parser():
    ap = _Parser(prog="corpus.py", add_help=False)
    sub = ap.add_subparsers(dest="comando", parser_class=_Parser)
    for nombre, comando in COMANDOS.items():
        comando.configurar(sub.add_parser(nombre, help=comando.ayuda, add_help=False))
    return ap


def _mostrar_error(e, s):
    if isinstance(e, AreaAmbigua):
        s.linea(f"AMBIGUO: '{e.texto}' coincide con varias áreas. Pregunta al usuario cuál es:")
        s.lista(f"{nombre} ({cod})" for cod, nombre in e.candidatos)
    elif isinstance(e, AreaNoEncontrada):
        s.linea(f"NO ENCONTRADO: no hay un área llamada '{e.texto}'. Áreas disponibles:")
        s.lista(f"{nombre} ({cod})" for cod, nombre in e.disponibles)
        if e.sin_documentos:
            s.linea("Áreas o entidades mencionadas sin documentos propios: " + ", ".join(e.sin_documentos))
    else:
        s.linea(f"ERROR: {e.mensaje}")


def main(argv=None, uso="", flujo=None):
    """Ejecuta un comando. Devuelve el codigo de salida (0 = correcto)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    s = Salida(flujo)
    if not argv or argv[0] not in COMANDOS:
        s.linea(uso)
        return 0 if not argv else 1
    try:
        args = crear_parser().parse_args(argv)
        u = resolver_ubicacion(RAIZ_SKILL)
        for aviso in u.avisos:
            s.linea("AVISO: " + aviso)
        corpus = cargar_corpus(u.contexto, incluir_no_vigentes(), u.documentos)
        COMANDOS[args.comando].ejecutar(Contexto(corpus, s), args)
    except CorpusError as e:
        _mostrar_error(e, s)
        return e.codigo_salida
    except BrokenPipeError:   # la salida se corto (p. ej. con | head): no es un error del corpus
        return 0
    return 0
