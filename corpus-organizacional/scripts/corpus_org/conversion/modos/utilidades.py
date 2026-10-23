"""Modos que no convierten: ``informe`` (regenera el informe HTML), ``matriz`` y ``diagnostico``."""

import sys
from pathlib import Path

from ... import VERSION
from ...comun.errores import CorpusError
from ...comun.estructura import CARPETA_PUBLICADA
from ...consulta.matriz import escribir_matriz
from ..extractores.ocr import diagnostico
from ..informe import generar_informe
from ..publicacion import escribir_huellas
from .base import CARPETA_SALIDA_CONSTRUCCION, Modo


class Informe(Modo):
    nombre = "informe"

    def ejecutar(self, args):
        """Regenera INFORME_CONSTRUCCION.html de la ultima construccion (sin volver a convertir)."""
        raiz = Path(args.salida) if args.salida else Path(args.entrada) / CARPETA_SALIDA_CONSTRUCCION
        if not (raiz / "control").is_dir():
            raise CorpusError(f"No hay una construcción en {raiz}: ejecute antes «construir».")
        print(f"Informe HTML: {generar_informe(raiz)}")


class Matriz(Modo):
    nombre = "matriz"

    def ejecutar(self, args):
        """Regenera la matriz Excel y sus CSV desde una construccion existente."""
        raiz = Path(args.salida or CARPETA_SALIDA_CONSTRUCCION).resolve()
        print(f"MATRIZ · convertir.py v{VERSION}")
        matriz = escribir_matriz(raiz)
        escribir_huellas(raiz / CARPETA_PUBLICADA)
        print(f"Matriz Excel y un CSV por hoja en: {matriz.parent}")
        print(f"Matriz Excel: {matriz}")


class Diagnostico(Modo):
    nombre = "diagnostico"

    def ejecutar(self, args):
        """Comprueba PyMuPDF, pytesseract, Pillow, Tesseract y el idioma español."""
        print(f"DIAGNÓSTICO · convertir.py v{VERSION}")
        lineas = diagnostico()
        for ok, texto in lineas:
            print(("OK     " if ok else "FALTA  ") + texto)
        if all(ok for ok, _ in lineas):
            print("\nTodo listo: las páginas escaneadas se leerán con OCR.")
        else:
            print("\nSin OCR las páginas escaneadas quedan sin texto (el resultado será REQUIERE REVISIÓN).")
            sys.exit(1)
