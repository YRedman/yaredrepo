"""Lectura de la estructura de un documento publicado (secciones, tablas y lineas de contenido).

Un solo recorrido del Markdown alimenta todas las vistas que necesitan los comandos.
"""

from dataclasses import dataclass
from typing import List

from ..comun.esquema import INICIO_TITULO_ENCABEZADO_PIE, RE_SECCION
from ..comun.markdown import celdas


@dataclass
class LineaContenido:
    seccion: str              # "Seccion › Subseccion"
    texto: str                # linea original
    cabecera: List[str]       # cabecera de la tabla a la que pertenece (vacia si no es tabla)
    es_cabecera: bool = False

    @property
    def es_tabla(self):
        return self.texto.startswith("|")


def es_seccion_encabezado_pie(titulo):
    """La seccion final con el encabezado y pie del original no es contenido del documento."""
    return INICIO_TITULO_ENCABEZADO_PIE in titulo


def lineas_contenido(doc):
    """Lineas con texto del documento, sin metadatos (>) ni el bloque de encabezado y pie."""
    if doc is None:
        return
    principal, sub = "", ""
    cab = []
    lineas = doc.lineas
    for k, l in enumerate(lineas[1:], 1):
        if l.startswith(">"):
            continue
        m = RE_SECCION.match(l)
        if m:
            titulo = m.group(2).strip()
            if es_seccion_encabezado_pie(titulo):
                return
            if len(m.group(1)) == 3:
                principal, sub = titulo, ""
            else:
                sub = titulo
            cab = []
            continue
        if not l.strip() or l.startswith("|---"):
            if not l.startswith("|"):
                cab = []
            continue
        seccion = principal + (" › " + sub if sub else "")
        if l.startswith("|"):
            if k + 1 < len(lineas) and lineas[k + 1].startswith("|---"):
                cab = celdas(l)
                yield LineaContenido(seccion, l, cab, es_cabecera=True)
                continue
            yield LineaContenido(seccion, l, cab)
        else:
            cab = []
            yield LineaContenido(seccion, l, [])


def celdas_contenido(doc):
    """(seccion, columna, texto, linea) por celda de tabla (sin cabeceras) o por linea de texto."""
    for lc in lineas_contenido(doc):
        if lc.es_cabecera:
            continue
        if lc.es_tabla:
            for j, x in enumerate(celdas(lc.texto)):
                yield lc.seccion, lc.cabecera[j] if j < len(lc.cabecera) else "", x, lc.texto
        else:
            yield lc.seccion, "", lc.texto, lc.texto


def secciones(doc):
    """Secciones de primer nivel: [(titulo, [lineas])], incluyendo sus subsecciones."""
    res = []
    if doc is None:
        return res
    for l in doc.lineas[1:]:
        if l.startswith(">"):
            continue
        m = RE_SECCION.match(l)
        if m and len(m.group(1)) == 3:
            res.append((m.group(2).strip(), []))
        elif res:
            res[-1][1].append(l)
        elif l.strip():
            res.append(("(sin título)", [l]))
    return res
