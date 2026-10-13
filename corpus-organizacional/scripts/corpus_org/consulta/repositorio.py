"""Carga del corpus publicado: indice, Markdown e inventario."""

import collections
from pathlib import Path

from ..comun.archivos import leer_csv
from ..comun.errores import CorpusError
from ..comun.esquema import (ARCHIVO_AREAS_EXTRA, ARCHIVO_INDICE, ARCHIVO_INVENTARIO, ARCHIVO_KPIS, ARCHIVO_RESUMEN,
                             COLUMNAS_INDICE, PREFIJO_DIC, PREFIJO_REPORTE, RE_TITULO_DOC, area_de,
                             INVENTARIO_RETIRADO, estado_no_publicable, inventario_activo, tipo_desde_texto)
from ..comun.estructura import CARPETA_DATOS, SKILL_CONTEXTO, SKILL_DOCUMENTOS, markdown_de_documentos
from ..comun.tipos import TIPOS_AREA, es_general, tipo as tipo_documento
from . import parser
from .areas import construir_alias
from .entidades import leer_areas_extra
from .modelo import Area, DocumentoCorpus


class Corpus:
    """Corpus publicado en memoria. Solo lectura; no imprime ni termina el programa."""

    def __init__(self, carpeta, meta, docs, archivos_md, inventario, fuente_indice, duplicados, excluidos,
                 extra=(), exclusiones=(), kpis=(), carpeta_documentos=None):
        self.carpeta = carpeta              # datos/ del skill corpus-contexto
        self.carpeta_documentos = carpeta_documentos   # skill corpus-documentos (None: todo en ``carpeta``)
        self.meta = meta                    # codigo -> fila del indice
        self.docs = docs                    # codigo -> DocumentoCorpus
        self.archivos_md = archivos_md
        self.inventario = inventario_activo(inventario)   # documentos que deben existir
        self.retirados = [f for f in inventario                             # solo reservan su codigo
                          if (f.get("estado_inventario") or "").upper() == INVENTARIO_RETIRADO]
        self.fuente_indice = fuente_indice
        self.duplicados = duplicados
        self.excluidos = excluidos          # codigo -> estado documental (no publicables)
        self.extra = list(extra)            # EntidadExtra: areas y entidades sin documentos
        self.exclusiones = list(exclusiones)
        self.kpis = list(kpis)
        self.areas = _construir_areas(meta, docs, self.inventario)
        self.alias = construir_alias(self.areas, [d for c, d in docs.items() if es_general(c)], self.extra)

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
        return sorted(c for c in self.docs if es_general(c))

    def inventario_de_area(self, cod):
        return [f for f in self.inventario if (f.get("codigo_departamento") or "").upper() == cod]

    def codigos_inventario(self):
        return {(f.get("codigo") or "").upper() for f in self.inventario if f.get("codigo")}

    @property
    def completo(self):
        """Hay inventario y todo lo inventariado esta convertido (o excluido por estado).

        Solo con el corpus completo se puede afirmar una ausencia ("este rol no tiene descriptivo").
        """
        return bool(self.inventario) and not self.faltantes_de_inventario()

    def cobertura(self, cod=None):
        """'X/Y descriptivos de puesto · Z/W procedimientos…' contra el inventario (de un area o de todo
        el corpus). Los tipos sin documentos ni inventario no se muestran (salvo descriptivos y procedimientos)."""
        partes = []
        for tipo in TIPOS_AREA:
            nombre = tipo_documento(tipo).plural.lower()
            esperados = [f for f in (self.inventario_de_area(cod) if cod else self.inventario)
                         if _tipo_inventario(f) == tipo]
            presentes = [c for c in (self.areas[cod].codigos(tipo) if cod else self.docs)
                         if c in self.docs and c.split("-")[0] == tipo]
            if not esperados and not presentes and tipo not in ("DES", "PRD"):
                continue
            if not self.inventario:
                partes.append(f"{len(presentes)} {nombre} (sin inventario: no se puede confirmar)")
                continue
            excluidos = [f for f in esperados if (f.get("codigo") or "").upper() in self.excluidos]
            partes.append(f"{len(presentes)}/{len(esperados)} {nombre}"
                          + (f" ({len(excluidos)} excluido{'s' if len(excluidos) > 1 else ''} por estado documental)"
                             if excluidos else ""))
        return " · ".join(partes)

    def faltantes_de_inventario(self, filas=None):
        """Codigos del inventario sin texto publicado (los excluidos por estado no cuentan como faltantes)."""
        filas = self.inventario if filas is None else filas
        return sorted(c for c in ((f.get("codigo") or "").upper() for f in filas)
                      if c and c not in self.docs and c not in self.excluidos)


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def _tipo_inventario(fila):
    return tipo_desde_texto(fila.get("tipo")) or (fila.get("codigo") or "").split("-")[0].upper()


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


def _leer_markdown(archivos, carpeta_documentos=None):
    docs, duplicados = {}, []
    for p in archivos:
        try:
            nombre = p.relative_to(carpeta_documentos).as_posix() if carpeta_documentos else p.name
        except ValueError:
            nombre = p.name
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
            docs[c] = DocumentoCorpus(c, nombre, i, fin, m.group(2).strip(), ls, p)
    return docs, duplicados


def _construir_areas(meta, docs, inventario):
    areas = collections.OrderedDict()
    for c in sorted(set(meta) | set(docs)):
        if es_general(c):
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


def cargar_corpus(carpeta, incluir_no_vigentes=False, documentos=None):
    """Lee el corpus publicado: ``carpeta`` es datos/ del skill corpus-contexto (indice, inventario y
    documentos generales) y ``documentos`` la carpeta del skill corpus-documentos. Si ``carpeta`` es
    salida_corpus/publicado/ se usan sus dos skills. Los documentos con estado no publicable se separan
    en ``excluidos``: la exclusion se aplica al indice y al texto a la vez; asi un documento obsoleto no
    aparece en busquedas ni se reporta como "documento sin fila en el indice".
    """
    carpeta = Path(carpeta)
    if (carpeta / SKILL_CONTEXTO / CARPETA_DATOS).is_dir():
        documentos = documentos or carpeta / SKILL_DOCUMENTOS
        carpeta = carpeta / SKILL_CONTEXTO / CARPETA_DATOS
    if not carpeta.is_dir():
        raise CorpusError(f"No existe la carpeta de datos: {carpeta}")
    documentos = Path(documentos) if documentos else None
    archivos_md = (markdown_de_documentos(documentos) if documentos else []) \
        + sorted(p for p in carpeta.glob("*.md") if _es_markdown_de_datos(p))
    meta, dup_indice, fuente, hay_indice = _leer_indice(carpeta)
    if not archivos_md and not hay_indice:
        raise CorpusError(f"El corpus está vacío: {carpeta} no contiene Markdown ni índice.")
    docs, dup_md = _leer_markdown(archivos_md, documentos)
    excluidos = {}
    if not incluir_no_vigentes:
        excluidos = {c: f.get("estado_documental", "") for c, f in meta.items()
                     if estado_no_publicable(f.get("estado_documental", ""))}
        meta = {c: f for c, f in meta.items() if c not in excluidos}
        docs = {c: d for c, d in docs.items() if c not in excluidos}
    inv = carpeta / ARCHIVO_INVENTARIO
    inventario = leer_csv(inv) if inv.is_file() else []
    extra, exclusiones = leer_areas_extra(carpeta / ARCHIVO_AREAS_EXTRA)
    kp = carpeta / ARCHIVO_KPIS
    kpis = leer_csv(kp) if kp.is_file() else []
    return Corpus(carpeta, meta, docs, archivos_md, inventario, fuente, dup_indice + dup_md, excluidos,
                  extra, exclusiones, kpis, documentos)
