"""Ubicacion de los skills fuente-contexto (indice, contexto, matriz) y fuente-documentos.

En Copilot un skill solo esta en disco despues de que el agente lo carga, y los skills cargados quedan
juntos en /home/oai/skills/appCatalog/<carpeta>/<skill>/. La <carpeta> cambia, asi que no hay rutas fijas.
Solo usa la biblioteca estandar.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..comun.errores import CorpusError
from ..comun.estructura import (CARPETA_INDICE, CARPETA_PUBLICADA, RAIZ_SKILLS_COPILOT, SKILL_CONTEXTO,
                                SKILL_DOCUMENTOS)
from ..comun.tipos import TIPOS_AREA

VARIABLE_DATOS = "CORPUS_DATOS"
VARIABLE_NO_VIGENTES = "CORPUS_INCLUIR_NO_VIGENTES"
NIVELES_ANCESTROS = 4      # carpetas hacia arriba donde se busca por nombre
MENSAJE_SIN_DOCUMENTOS = ("no encuentro el skill fuente-documentos. Carga primero fuente-contexto y "
                          "fuente-documentos (lee su SKILL.md) y vuelve a ejecutar.")
MENSAJE_SIN_CONTEXTO = ("no encuentro el skill fuente-contexto. Carga primero fuente-contexto y "
                        "fuente-documentos (lee su SKILL.md) y vuelve a ejecutar.")


@dataclass
class Ubicacion:
    contexto: Path                          # carpeta fuente-contexto
    documentos: Path                        # carpeta fuente-documentos
    buscados: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)


def _es_contexto(q):
    return q.is_dir() and (q / CARPETA_INDICE).is_dir()


def _es_documentos(q):
    return q.is_dir() and any((q / t).is_dir() for t in TIPOS_AREA)


def _con_nombre(q, nombre):
    """``q`` si se llama ``nombre``, o su subcarpeta de ese nombre."""
    return q if q.name == nombre else q / nombre


def _expandir(patron):
    """Carpetas que cumplen un patron con un '*' (una carpeta <carpeta> desconocida)."""
    partes = patron.parts
    if "*" not in partes:
        return [patron] if patron.is_dir() else []
    i = partes.index("*")
    base = Path(*partes[:i])
    if not base.is_dir():
        return []
    try:
        return sorted(p for p in base.glob(str(Path("*", *partes[i + 1:]))) if p.is_dir())
    except OSError:
        return []


MAX_CARPETAS_RECORRIDAS = 20000     # tope de la busqueda de ultimo recurso por el disco
PROFUNDIDAD_BUSQUEDA = 5


def _raices_de_busqueda():
    """Carpetas donde un skill puede estar: la de skills de Copilot (appCatalog), su carpeta madre (alguien puede
    haberlos copiado directo en /home/oai/skills) y las de adjuntos."""
    return [RAIZ_SKILLS_COPILOT, RAIZ_SKILLS_COPILOT.parent, Path("/mnt/data"), Path("/mnt/user-data")]


def _recorrer(raiz, nombre, comprobar):
    """Carpetas ``nombre`` hasta PROFUNDIDAD_BUSQUEDA niveles bajo ``raiz`` (ultimo recurso: la carpeta intermedia de
    appCatalog cambia y a veces hay mas de un nivel)."""
    halladas, vistas = [], 0
    if not raiz.is_dir():
        return halladas
    base = len(raiz.parts)
    for actual, dirs, _ in os.walk(raiz):
        vistas += 1
        if vistas > MAX_CARPETAS_RECORRIDAS or len(Path(actual).parts) - base >= PROFUNDIDAD_BUSQUEDA:
            dirs[:] = []
            if vistas > MAX_CARPETAS_RECORRIDAS:
                break
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "site-packages")]
        if nombre in dirs and comprobar(Path(actual) / nombre):
            halladas.append(Path(actual) / nombre)
    return halladas


def _buscar_por_nombre(nombre, comprobar, raiz_skill, u):
    """Carpetas ``nombre`` en las carpetas de skills de Copilot y en las superiores al skill actual; si no esta en
    ninguna ruta conocida, se recorre el disco (acotado) desde esas carpetas."""
    patrones = []
    for raiz in _raices_de_busqueda():
        patrones += [raiz / nombre, raiz / "*" / nombre, raiz / "*" / "*" / nombre]
    for anc in list(Path(raiz_skill).parents)[:NIVELES_ANCESTROS]:
        patrones += [anc / nombre, anc / "*" / nombre]
    for patron in patrones:
        u.buscados.append(str(patron))
        halladas = [q for q in _expandir(patron) if comprobar(q)]
        if halladas:
            return halladas
    for raiz in _raices_de_busqueda():
        u.buscados.append(f"{raiz}/** (hasta {PROFUNDIDAD_BUSQUEDA} niveles)")
        halladas = _recorrer(raiz, nombre, comprobar)
        if halladas:
            return halladas
    return []


def _desde_variable(entorno):
    """Carpetas que CORPUS_DATOS puede indicar: fuente-contexto, fuente-documentos o la que contiene ambas."""
    env = entorno.get(VARIABLE_DATOS)
    if not env:
        return None, None, None
    q = Path(env).expanduser()
    if q.name == SKILL_DOCUMENTOS and _es_documentos(q):      # se indico la carpeta de documentos: su hermana
        return q, (q.parent / SKILL_CONTEXTO if _es_contexto(q.parent / SKILL_CONTEXTO) else None), q
    contexto = _con_nombre(q, SKILL_CONTEXTO)
    documentos = _con_nombre(q, SKILL_DOCUMENTOS)
    if not _es_contexto(contexto):
        contexto = next((c for c in (q / CARPETA_PUBLICADA / SKILL_CONTEXTO,) if _es_contexto(c)), None)
        if contexto is None and _es_contexto(q):
            contexto = q
    if not _es_documentos(documentos):
        documentos = q / CARPETA_PUBLICADA / SKILL_DOCUMENTOS
        if not _es_documentos(documentos):
            documentos = q if _es_documentos(q) else None
    return q, contexto, documentos


def resolver_ubicacion(raiz_skill, entorno=None):
    """Ubicacion de fuente-contexto y fuente-documentos.

    fuente-contexto: la de ``CORPUS_DATOS`` si la indica; si no, el propio skill (``raiz_skill`` es la carpeta
    que contiene scripts/), y en el repositorio salida_corpus/copilot/fuente-contexto.
    fuente-documentos: la hermana de fuente-contexto; si no esta, ``CORPUS_DATOS`` y luego una busqueda por
    nombre. Si no se encuentra alguna, CorpusError con el mensaje que el agente sabe interpretar.
    """
    entorno = os.environ if entorno is None else entorno
    raiz_skill = Path(raiz_skill)
    q, contexto, documentos_env = _desde_variable(entorno)
    u = Ubicacion(None, None)
    if contexto is None:
        for c in (raiz_skill, raiz_skill / "salida_corpus" / CARPETA_PUBLICADA / SKILL_CONTEXTO,
                  raiz_skill / CARPETA_PUBLICADA / SKILL_CONTEXTO):
            if _es_contexto(c):
                contexto = c
                break
    if contexto is None:
        halladas = _buscar_por_nombre(SKILL_CONTEXTO, _es_contexto, raiz_skill, u)
        contexto = halladas[0] if halladas else None
    if contexto is None:
        raise CorpusError(MENSAJE_SIN_CONTEXTO)
    u.contexto = contexto.resolve()
    hermana = u.contexto.parent / SKILL_DOCUMENTOS
    u.buscados.append(str(hermana))
    if _es_documentos(hermana):
        u.documentos = hermana
        return u
    if documentos_env is not None:
        u.documentos = documentos_env.resolve()
        return u
    halladas = _buscar_por_nombre(SKILL_DOCUMENTOS, _es_documentos, raiz_skill, u)
    if not halladas:
        raise CorpusError(MENSAJE_SIN_DOCUMENTOS)
    halladas.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    u.documentos = halladas[0].resolve()
    if len(halladas) > 1:
        u.avisos.append(f"Hay {len(halladas)} carpetas {SKILL_DOCUMENTOS}; se usa la más reciente: {u.documentos}.")
    return u


def raiz_del_skill():
    """Carpeta que contiene scripts/: el skill fuente-contexto (o el repositorio)."""
    for p in Path(__file__).resolve().parents:
        if p.name == "scripts":
            return p.parent
    return Path(__file__).resolve().parents[3]


def describir_ubicacion(raiz_skill, entorno=None):
    """Lineas con donde estan fuente-contexto y fuente-documentos y como ejecutar corpus.py, aunque falte alguna."""
    raiz_skill = Path(raiz_skill)
    script = raiz_skill / "scripts" / "corpus.py"
    lineas = ["UBICACIÓN DEL CORPUS"]
    try:
        u = resolver_ubicacion(raiz_skill, entorno)
        lineas += [f"fuente-contexto: {u.contexto}", f"fuente-documentos: {u.documentos}"]
        lineas += ["AVISO: " + a for a in u.avisos]
        lineas += [f"corpus.py: {script}",
                   f'Ejecútalo desde cualquier carpeta: python "{script}" <comando>   (por ejemplo: verificar, catalogo)']
    except CorpusError as e:
        lineas += [f"fuente-contexto: {raiz_skill}", f"ERROR: {e.mensaje}",
                   "Para localizar el skill: find /home/oai/skills -type f -path '*fuente-contexto/scripts/corpus.py' 2>/dev/null"]
    return lineas


def incluir_no_vigentes(entorno=None):
    entorno = os.environ if entorno is None else entorno
    return entorno.get(VARIABLE_NO_VIGENTES, "").strip().lower() in ("1", "true", "si", "sí")
