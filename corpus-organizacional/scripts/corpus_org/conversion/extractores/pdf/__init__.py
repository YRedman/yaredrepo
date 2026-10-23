"""Extractor de PDF (PyMuPDF; pdfplumber y Tesseract son opcionales)."""

import re

from ....comun.texto import tokens
from ..base import Extractor
from .extraccion import ExtraccionPDF
from .lineas import importar_fitz
from .pliegos import separar_pliegos


# pdfplumber escribe "(cid:123)" cuando no puede traducir un glifo (vinetas, simbolos); no es texto del documento.
RE_CID = re.compile(r"\(cid:\d+\)")


def _tokens_pdfplumber(path, omitir_paginas):
    """Tokens que lee un segundo motor (pdfplumber), sin paginas escaneadas ni glifos sin traducir."""
    import pdfplumber
    cruz = set()
    with pdfplumber.open(path) as pl:
        for k, pg in enumerate(pl.pages):
            if (k + 1) in omitir_paginas:
                continue
            cruz.update(tokens(RE_CID.sub(" ", pg.extract_text() or "")))
    return cruz


class ExtractorPDF(Extractor):
    extensiones = (".pdf",)

    def __init__(self, verificacion_cruzada=True):
        self.verificacion_cruzada = verificacion_cruzada

    def extraer(self, path):
        fitz = importar_fitz()
        doc_pdf = fitz.open(str(path))
        try:
            if doc_pdf.needs_pass:
                raise RuntimeError("El PDF está protegido con contraseña.")
            doc_leido, origen = separar_pliegos(fitz, doc_pdf)
            try:
                d = ExtraccionPDF(fitz, doc_leido).ejecutar()
            finally:
                if doc_leido is not doc_pdf:
                    doc_leido.close()
        finally:
            doc_pdf.close()
        if origen != list(range(len(origen))):
            d.notas.append(f"PDF en pliegos: cada página apaisada se leyó como dos (izquierda y derecha); "
                           f"{len(set(origen))} páginas del archivo = {len(origen)} páginas del documento.")
        if self.verificacion_cruzada:
            try:
                omitir = {origen[k - 1] + 1 for k in set(d.paginas_ocr) | set(d.paginas_escaneadas_sin_ocr)
                          if 0 < k <= len(origen)}
                d.texto_cruzado = _tokens_pdfplumber(str(path), omitir)
            except Exception as e:
                d.notas.append(f"Verificación cruzada con pdfplumber no disponible: {e}")
        return d
