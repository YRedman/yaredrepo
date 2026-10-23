"""Linea de comandos de ``convertir.py``: interpreta los argumentos y ejecuta el modo pedido."""

import argparse
import sys

from ..comun.errores import CorpusError
from .entradas import entrada_por_defecto
from .modos import MODOS


def crear_parser():
    ap = argparse.ArgumentParser(description="Conversión y construcción del corpus organizacional.")
    sub = ap.add_subparsers(dest="modo", required=True)
    for nombre, modo in MODOS.items():
        sp = sub.add_parser(nombre)
        sp.add_argument("--entrada", default=None,
                        help="Carpeta donde están los archivos adjuntos (por defecto /mnt/data o la actual).")
        sp.add_argument("--salida", default=None, help="Carpeta de salida.")
        modo.configurar(sp)
    return ap


def main(argv=None):
    args = crear_parser().parse_args(argv)
    if args.entrada is None:
        args.entrada = entrada_por_defecto()
    try:
        MODOS[args.modo].ejecutar(args)
    except CorpusError as e:
        print(f"ERROR: {e.mensaje}")
        sys.exit(e.codigo_salida)
