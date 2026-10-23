"""Lineas de texto de una pagina PDF (con sus estilos) y utilidades de geometria comunes a los demas modulos."""

import os

from ....comun.texto import limpiar_celda, nfc, tokens
from ..maquetacion import agrupar_filas


def importar_fitz():
    os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")
    try:
        import pymupdf as fitz
    except ImportError:  # versiones antiguas de PyMuPDF solo exponen 'fitz'
        import fitz
    try:
        fitz.no_recommend_layout()
    except Exception:
        pass
    return fitz


def _es_bold(span):
    fuente = span["font"].lower()
    return bool(span["flags"] & 16) or "bold" in fuente or "black" in fuente


def lineas_pagina(page, fitz):
    d = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    lineas = []
    for b in d["blocks"]:
        for l in b.get("lines", []):
            spans = [s for s in l["spans"] if s["text"].strip()]
            if not spans:
                continue
            texto = "".join(s["text"] for s in l["spans"]).strip()
            x0, y0, x1, y1 = l["bbox"]
            lineas.append({
                "texto": nfc(texto), "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "tam": round(max(spans, key=lambda s: len(s["text"].strip()))["size"], 1),
                "bold": all(_es_bold(s) for s in spans), "font": spans[0]["font"], "spans": spans,
                "chars": sum(len(s["text"].strip()) for s in spans),
            })
    return lineas


def dentro(l, r, margen=1):
    cx, cy = (l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2
    return r.x0 - margen <= cx <= r.x1 + margen and r.y0 - margen <= cy <= r.y1 + margen


def texto_zona(page, fitz, lineas, rect):
    """Texto de una zona de encabezado o pie: celdas de tabla completas y luego lineas sueltas."""
    textos, rects = [], []
    try:
        for t in page.find_tables(clip=rect).tables:
            rects.append(fitz.Rect(t.bbox))
            for fila in t.extract():
                for c in fila:
                    c = limpiar_celda(c) if c else ""
                    if c and c not in textos:
                        textos.append(c)
    except Exception:
        pass
    resto = [l for l in lineas if not any(dentro(l, r) for r in rects)]
    for f in agrupar_filas(resto):
        if f["texto"] not in textos:
            textos.append(f["texto"])
    return textos


def palabras_ocr(lineas):
    """Palabras de las lineas OCR, incluidas las que se unen al quitar el guion de fin de linea ("ambien-" + "tal")."""
    lineas = list(lineas)
    palabras = set()
    for k, texto in enumerate(lineas):
        palabras.update(tokens(texto))
        if texto.rstrip().endswith("-") and k + 1 < len(lineas):
            antes, despues = tokens(texto), tokens(lineas[k + 1])
            if antes and despues:
                palabras.add(antes[-1] + despues[0])
    return palabras
