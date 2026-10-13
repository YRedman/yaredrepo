"""Ubicacion de las carpetas del corpus publicado: datos/ (skill corpus-contexto) y el skill corpus-documentos.

En Copilot cada skill queda en /home/oai/skills/appCatalog/<id>/<nombre-skill>/ y el <id> cambia, por eso
la carpeta de documentos se busca por el nombre del skill. Solo usa la biblioteca estandar.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..comun.errores import CorpusError
from ..comun.esquema import ARCHIVO_INDICE, ARCHIVO_INVENTARIO
from ..comun.estructura import (CARPETA_DATOS, RAIZ_SKILLS_COPILOT, SKILL_CONTEXTO, SKILL_DOCUMENTOS,
                                markdown_de_documentos)
from ..comun.tipos import RE_ARCHIVO_DOCUMENTOS, TIPOS_AREA

VARIABLE_DATOS = "CORPUS_DATOS"
VARIABLE_DOCUMENTOS = "CORPUS_DOCUMENTOS"
VARIABLE_NO_VIGENTES = "CORPUS_INCLUIR_NO_VIGENTES"
NIVELES_ANCESTROS = 4      # carpetas hacia arriba donde se busca un skill hermano


@dataclass
class Ubicacion:
    datos: Path
    documentos: Optional[Path]
    buscados: List[str] = field(default_factory=list)   # lugares revisados para corpus-documentos
    avisos: List[str] = field(default_factory=list)


def _datos_en(carpeta):
    """La carpeta datos/ dentro de ``carpeta`` si es un publicado/, un skill corpus-contexto o ya es datos/."""
    for q in (carpeta / SKILL_CONTEXTO / CARPETA_DATOS, carpeta / CARPETA_DATOS, carpeta):
        if q.is_dir() and _parece_datos(q):
            return q
    return None


def _parece_datos(q):
    return ((q / ARCHIVO_INDICE).is_file() or (q / ARCHIVO_INVENTARIO).is_file()
            or any(RE_ARCHIVO_DOCUMENTOS.match(p.name) or p.name == "contexto.md" for p in q.glob("*.md")))


def resolver_carpeta_datos(raiz_skill, entorno=None):
    """Carpeta datos/ del corpus: ``CORPUS_DATOS``, la del propio skill (corpus-contexto/datos), la de
    salida_corpus/publicado/ en el repositorio o, por compatibilidad, un publicado/ plano anterior."""
    entorno = os.environ if entorno is None else entorno
    env = entorno.get(VARIABLE_DATOS)
    opciones = [Path(env).expanduser() if env else None, raiz_skill,
                raiz_skill / "salida_corpus" / "publicado", raiz_skill / "publicado"]
    for q in opciones:
        if q is not None and q.is_dir():
            datos = _datos_en(q)
            if datos is not None:
                return datos.resolve()
    if env:
        return Path(env).expanduser().resolve()
    return (raiz_skill / CARPETA_DATOS).resolve()


def _es_documentos(q):
    return q.is_dir() and any(p.is_dir() and p.name in TIPOS_AREA for p in q.iterdir())


def _candidatos_documentos(raiz_skill, datos):
    """Lugares donde puede estar el skill corpus-documentos, en orden de preferencia."""
    vistos = []

    def agregar(q):
        if q not in vistos:
            vistos.append(q)

    # mismo publicado/ (repositorio) o skills hermanos con el mismo <id>
    agregar(datos.parent.parent / SKILL_DOCUMENTOS)
    agregar(raiz_skill.parent / SKILL_DOCUMENTOS)
    # Copilot: /home/oai/skills/appCatalog/<id>/corpus-documentos (el <id> cambia)
    agregar(RAIZ_SKILLS_COPILOT / SKILL_DOCUMENTOS)
    agregar(RAIZ_SKILLS_COPILOT / "*" / SKILL_DOCUMENTOS)
    # carpetas superiores a la del skill (otra instalacion de skills con otra raiz)
    for anc in list(raiz_skill.parents)[:NIVELES_ANCESTROS]:
        agregar(anc / SKILL_DOCUMENTOS)
        agregar(anc / "*" / SKILL_DOCUMENTOS)
    return vistos


def _expandir(q):
    if "*" not in q.parts:
        return [q] if q.is_dir() else []
    i = q.parts.index("*")
    base = Path(*q.parts[:i])
    if not base.is_dir():
        return []
    try:
        return sorted(p for p in base.glob(str(Path(*q.parts[i:]))) if p.is_dir())
    except OSError:
        return []


def _md_planos(datos):
    """Markdown de documentos de area en un publicado/ plano anterior (DES_SEG.md, D_SEG.md...)."""
    def de_area(nombre):
        m = RE_ARCHIVO_DOCUMENTOS.match(nombre)
        return (m and m.group(1) in TIPOS_AREA) or nombre[:2] in ("D_", "P_")
    return [p for p in datos.glob("*.md") if de_area(p.name)]


def resolver_ubicacion(raiz_skill, entorno=None):
    """Ubicacion de datos/ y del skill corpus-documentos. Error claro si no se encuentra corpus-documentos."""
    entorno = os.environ if entorno is None else entorno
    datos = resolver_carpeta_datos(raiz_skill, entorno)
    u = Ubicacion(datos, None)
    env = entorno.get(VARIABLE_DOCUMENTOS)
    if env:
        q = Path(env).expanduser()
        u.buscados.append(f"{VARIABLE_DOCUMENTOS}={q}")
        if q.is_dir():
            u.documentos = q.resolve()
            return u
    encontrados = []
    for patron in _candidatos_documentos(raiz_skill, datos):
        u.buscados.append(str(patron))
        for q in _expandir(patron):
            if _es_documentos(q) and q.resolve() not in encontrados:
                encontrados.append(q.resolve())
        if encontrados:
            break
    if encontrados:
        encontrados.sort(key=lambda q: max((p.stat().st_mtime for p in markdown_de_documentos(q)), default=0),
                         reverse=True)
        u.documentos = encontrados[0]
        if len(encontrados) > 1:
            u.avisos.append(f"Hay {len(encontrados)} carpetas {SKILL_DOCUMENTOS}; se usa la más reciente: "
                            f"{u.documentos} (otras: {', '.join(map(str, encontrados[1:]))}).")
        return u
    if datos.is_dir() and _md_planos(datos):
        return u      # publicado/ plano de una version anterior: documentos y datos en la misma carpeta
    raise CorpusError(
        f"No encontré la carpeta del skill «{SKILL_DOCUMENTOS}» (documentos DES/, PRD/, PRO/, POL/). "
        f"Datos del corpus: {datos}. Busqué en: " + "; ".join(u.buscados)
        + f". Instale el skill {SKILL_DOCUMENTOS} o indique su carpeta en la variable {VARIABLE_DOCUMENTOS}.")


def incluir_no_vigentes(entorno=None):
    entorno = os.environ if entorno is None else entorno
    return entorno.get(VARIABLE_NO_VIGENTES, "").strip().lower() in ("1", "true", "si", "sí")
