"""Extractor de transcripciones manuales (.md, .csv, .txt) usadas como material de contexto.

Sirve para el contenido que en el original esta en imagenes (capturas de tableros, minutas
escaneadas) y se transcribio a mano. Reconoce Markdown simple: titulos (#), listas (-, *, 1.) y
tablas (|). Un CSV se convierte en una tabla.
"""

import collections
import csv
import io
import re
from pathlib import Path

from ...comun.archivos import detectar_delimitador, leer_texto
from ...comun.esquema import RE_MARCAS
from ...comun.texto import numeros, tokens
from ..modelo import DocumentoExtraido, bloque_h
from .base import Extractor

RE_TITULO = re.compile(r"^(#{1,6})\s+(.*)$")
RE_ITEM = re.compile(r"^(\s*)(?:[-*•]|\d+[.)])\s+(.*)$")
RE_SEPARADOR_TABLA = re.compile(r"^\|\s*:?-{3,}")


def _filas_csv(txt):
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")      # CSV de Excel para Mac o con saltos \r sueltos
    lineas = txt.splitlines()
    if not lineas:
        return []
    filas = csv.reader(io.StringIO(txt), delimiter=detectar_delimitador(lineas[0]))
    return [f for f in filas if any(c.strip() for c in f)]


def _bloques_markdown(txt):
    bloques, parrafo, tabla = [], [], []

    def cerrar_parrafo():
        if parrafo:
            bloques.append({"k": "p", "texto": " ".join(parrafo)})
            parrafo.clear()

    def cerrar_tabla():
        if tabla:
            bloques.append({"k": "tabla", "filas": list(tabla)})
            tabla.clear()

    for linea in txt.splitlines():
        l = linea.rstrip()
        if l.startswith("|"):
            cerrar_parrafo()
            if not RE_SEPARADOR_TABLA.match(l):
                tabla.append([c.strip() for c in re.split(r"(?<!\\)\|", l.strip().strip("|"))])
            continue
        cerrar_tabla()
        m = RE_TITULO.match(l)
        if m:
            cerrar_parrafo()
            bloques.append(bloque_h(min(len(m.group(1)), 3), m.group(2).strip()))
            continue
        m = RE_ITEM.match(l)
        if m:
            cerrar_parrafo()
            bloques.append({"k": "li", "marcador": "-", "texto": m.group(2).strip(),
                            "nivel": min(len(m.group(1)) // 2, 3)})
            continue
        if l.strip():
            parrafo.append(l.strip())
        else:
            cerrar_parrafo()
    cerrar_parrafo()
    cerrar_tabla()
    return bloques


class ExtractorTexto(Extractor):
    extensiones = (".md", ".csv", ".txt")

    def extraer(self, path):
        txt = leer_texto(path)
        d = DocumentoExtraido()
        # las marcas ([NO ESPECIFICADO], [D-XXX-01]...) se descuentan igual que en el Markdown generado
        d.crudo = collections.Counter(tokens(RE_MARCAS.sub(" ", txt)))
        d.numeros = numeros(txt)
        if Path(path).suffix.lower() == ".csv":
            filas = _filas_csv(txt)
            d.bloques = [{"k": "tabla", "filas": filas}] if filas else []
        else:
            d.bloques = _bloques_markdown(txt)
        d.tablas = sum(1 for b in d.bloques if b["k"] == "tabla")
        return d
