"""Carga del corpus publicado: indice, Markdown e inventario."""

import collections

from ..comun.archivos import leer_csv
from ..comun.errores import CorpusError
from ..comun.esquema import (ARCHIVO_INDICE, ARCHIVO_INVENTARIO, ARCHIVO_RESUMEN, COLUMNAS_INDICE,
                             PREFIJO_DIC, PREFIJO_REPORTE, RE_TITULO_DOC, area_de, estado_no_publicable)
from . import parser
from .areas import construir_alias
from .modelo import Area, DocumentoCorpus


class Corpus:
    """Corpus publicado en memoria. Solo lectura; no imprime ni termina el programa."""

    def __init__(self, carpeta, meta, docs, archivos_md, inventario, fuente_indice, duplicados, excluidos):
        self.carpeta = carpeta
        self.meta = meta                    # codigo -> fila del indice
        self.docs = docs                    # codigo -> DocumentoCorpus
        self.archivos_md = archivos_md
        self.inventario = inventario
        self.fuente_indice = fuente_indice
        self.duplicados = duplicados
        self.excluidos = excluidos          # codigo -> estado documental (no publicables)
        self.areas = _construir_areas(meta, docs, inventario)
        self.alias = construir_alias(self.areas, [d for c, d in docs.items() if c.startswith("C-")])

    # -- consultas basicas -----------------------------------------------------

    def nombre(self, c):
        f = self.meta.get(c, {})
        d = self.docs.get(c)
        return f.get("nombre_puesto") or f.get("nombre") or (d.titulo if d else "")

    def doc(self, c):
        return self.docs.get(c)

    def cuerpo(self, c):
        """[(seccion, linea)] del contenido del documento."""
        return [(lc.seccion, lc.texto) for lc in parser.lineas_contenido(self.docs.get(c))]

    def secciones(self, c):
        return parser.secciones(self.docs.get(c))

    def celdas(self, c):
        return parser.celdas_contenido(self.docs.get(c))

    def contexto(self):
        return sorted(c for c in self.docs if c.startswith("C-"))

    def inventario_de_area(self, cod):
        return [f for f in self.inventario if (f.get("codigo_departamento") or "").upper() == cod]

    def codigos_inventario(self):
        return {(f.get("codigo") or "").upper() for f in self.inventario if f.get("codigo")}

    def faltantes_de_inventario(self, filas=None):
        """Codigos del inventario sin texto publicado (los excluidos por estado no cuentan como faltantes)."""
        filas = self.inventario if filas is None else filas
        return sorted(c for c in ((f.get("codigo") or "").upper() for f in filas)
                      if c and c not in self.docs and c not in self.excluidos)


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def _es_markdown_de_datos(p):
    return not p.name.upper().startswith((PREFIJO_REPORTE, ARCHIVO_RESUMEN.rsplit(".", 1)[0]))


def _leer_indice(carpeta):
    indice = carpeta / ARCHIVO_INDICE
    if indice.is_file():
        fuentes, nombre = [indice], indice.name
    else:
        fuentes, nombre = sorted(carpeta.glob(f"{PREFIJO_DIC}*.csv")), f"{PREFIJO_DIC}*.csv (compatibilidad)"
    meta, duplicados = {}, []
    for p in fuentes:
        for f in leer_csv(p, columnas_si_no_hay_encabezado=COLUMNAS_INDICE):
            c = (f.get("codigo") or "").strip().upper()
            if not c:
                continue
            if c in meta:
                duplicados.append(c)
            meta[c] = f
    return meta, duplicados, nombre, bool(fuentes)


def _leer_markdown(archivos):
    docs, duplicados = {}, []
    for p in archivos:
        lineas = p.read_text(encoding="utf-8", errors="replace").splitlines()
        inicios = [(i, RE_TITULO_DOC.match(l)) for i, l in enumerate(lineas)]
        inicios = [(i, m) for i, m in inicios if m]
        for k, (i, m) in enumerate(inicios):
            fin = inicios[k + 1][0] if k + 1 < len(inicios) else len(lineas)
            c = m.group(1).upper()
            if c in docs:
                duplicados.append(c)
            ls = lineas[i:fin]
            while ls and ls[-1].strip() in ("", "---"):
                ls.pop()
            docs[c] = DocumentoCorpus(c, p.name, i, fin, m.group(2).strip(), ls)
    return docs, duplicados


def _construir_areas(meta, docs, inventario):
    areas = collections.OrderedDict()
    for c in sorted(set(meta) | set(docs)):
        if c.startswith("C-"):
            continue
        cod = area_de(c)
        nombre = (meta.get(c, {}).get("departamento") or "").strip()
        a = areas.setdefault(cod, Area(cod, nombre))
        if nombre and not a.nombre:
            a.nombre = nombre
        a.agregar(c)
    for f in inventario:
        cod = (f.get("codigo_departamento") or "").strip().upper()
        if cod and cod not in areas:
            areas[cod] = Area(cod, f.get("departamento", ""))
    return areas


def cargar_corpus(carpeta, incluir_no_vigentes=False):
    """Lee la carpeta publicada. Los documentos con estado no publicable se separan en ``excluidos``.

    La exclusion se aplica al indice y al texto a la vez; asi un documento obsoleto no aparece
    en busquedas ni se reporta como "documento sin fila en el indice".
    """
    if not carpeta.is_dir():
        raise CorpusError(f"No existe la carpeta de datos: {carpeta}")
    archivos_md = sorted(p for p in carpeta.glob("*.md") if _es_markdown_de_datos(p))
    meta, dup_indice, fuente, hay_indice = _leer_indice(carpeta)
    if not archivos_md and not hay_indice:
        raise CorpusError(f"El corpus está vacío: {carpeta} no contiene Markdown ni índice.")
    docs, dup_md = _leer_markdown(archivos_md)
    excluidos = {}
    if not incluir_no_vigentes:
        excluidos = {c: f.get("estado_documental", "") for c, f in meta.items()
                     if estado_no_publicable(f.get("estado_documental", ""))}
        meta = {c: f for c, f in meta.items() if c not in excluidos}
        docs = {c: d for c, d in docs.items() if c not in excluidos}
    inv = carpeta / ARCHIVO_INVENTARIO
    inventario = leer_csv(inv) if inv.is_file() else []
    return Corpus(carpeta, meta, docs, archivos_md, inventario, fuente, dup_indice + dup_md, excluidos)
