"""Ubicacion del skill fuente-corpus (documentos/, contexto/, indice/, matriz/, scripts/).

En Copilot un skill solo esta en disco despues de que el agente lo carga, y los skills cargados quedan
juntos en /home/oai/skills/appCatalog/<carpeta>/<skill>/. La <carpeta> cambia, asi que no hay rutas fijas.
Tambien se reconoce la estructura anterior (dos skills: fuente-contexto y fuente-documentos).
Solo usa la biblioteca estandar.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..comun.errores import CorpusError
from ..comun.estructura import (CARPETA_DOCUMENTOS, CARPETA_INDICE, CARPETA_PUBLICADA, RAIZ_SKILLS_COPILOT,
                                SKILL_CONTEXTO, SKILL_CORPUS, SKILL_DOCUMENTOS)
from ..comun.tipos import TIPOS_AREA

VARIABLE_DATOS = "CORPUS_DATOS"
VARIABLE_NO_VIGENTES = "CORPUS_INCLUIR_NO_VIGENTES"
NIVELES_ANCESTROS = 4      # carpetas hacia arriba donde se busca por nombre
MENSAJE_SIN_CONTEXTO = ("no encuentro el skill fuente-corpus. Carga primero el skill fuente-corpus "
                        "(lee su SKILL.md) y vuelve a ejecutar.")
MENSAJE_SIN_DOCUMENTOS = ("no encuentro la carpeta documentos del skill fuente-corpus. Vuelve a cargar el skill "
                          "fuente-corpus completo (lee su SKILL.md) y vuelve a ejecutar.")


@dataclass
class Ubicacion:
    contexto: Path                          # carpeta del skill fuente-corpus
    documentos: Path                        # fuente-corpus/documentos (o el skill fuente-documentos de la estructura anterior)
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


def _documentos_del_skill(skill):
    """``skill/documentos`` si tiene las carpetas de tipo (DES, PRD...); None si no."""
    d = skill / CARPETA_DOCUMENTOS
    return d if _es_documentos(d) else None


def _skill_en(q):
    """La carpeta del skill dentro de ``q`` (o ``q`` mismo): fuente-corpus o, en la estructura anterior, fuente-contexto."""
    for c in (q, q / SKILL_CORPUS, q / CARPETA_PUBLICADA / SKILL_CORPUS, q / SKILL_CONTEXTO,
              q / CARPETA_PUBLICADA / SKILL_CONTEXTO):
        if _es_contexto(c):
            return c
    return None


def _desde_variable(entorno):
    """(carpeta indicada, skill, documentos aparte) que CORPUS_DATOS puede indicar: el skill fuente-corpus, la carpeta
    que lo contiene o, en la estructura anterior, fuente-contexto / fuente-documentos."""
    env = entorno.get(VARIABLE_DATOS)
    if not env:
        return None, None, None
    q = Path(env).expanduser()
    if q.name == SKILL_DOCUMENTOS and _es_documentos(q):          # estructura anterior: se indico la de documentos
        hermana = q.parent / SKILL_CONTEXTO
        return q, (hermana if _es_contexto(hermana) else None), q
    skill = _skill_en(q)
    documentos = None
    if skill is not None and _documentos_del_skill(skill) is None:
        for c in (q / SKILL_DOCUMENTOS, q / CARPETA_PUBLICADA / SKILL_DOCUMENTOS, skill.parent / SKILL_DOCUMENTOS):
            if _es_documentos(c):
                documentos = c
                break
    return q, skill, documentos


def resolver_ubicacion(raiz_skill, entorno=None):
    """Ubicacion del skill fuente-corpus (indice/, contexto/, matriz/ y documentos/).

    El skill: el de ``CORPUS_DATOS`` si lo indica; si no, el propio (``raiz_skill`` es la carpeta que contiene
    scripts/), y en el repositorio salida_corpus/copilot/fuente-corpus; si no, se busca por nombre. Los documentos
    estan en ``documentos/`` dentro del skill; con la estructura anterior (dos skills) se buscan en el skill
    fuente-documentos hermano, en ``CORPUS_DATOS`` y por nombre. Si no se encuentra algo, CorpusError con el mensaje
    que el agente sabe interpretar.
    """
    entorno = os.environ if entorno is None else entorno
    raiz_skill = Path(raiz_skill)
    _q, contexto, documentos_env = _desde_variable(entorno)
    u = Ubicacion(None, None)
    if contexto is None:
        for c in (raiz_skill, raiz_skill / "salida_corpus" / CARPETA_PUBLICADA / SKILL_CORPUS,
                  raiz_skill / CARPETA_PUBLICADA / SKILL_CORPUS, raiz_skill / "salida_corpus" / CARPETA_PUBLICADA / SKILL_CONTEXTO,
                  raiz_skill / CARPETA_PUBLICADA / SKILL_CONTEXTO):
            if _es_contexto(c):
                contexto = c
                break
    if contexto is None:
        for nombre in (SKILL_CORPUS, SKILL_CONTEXTO):
            halladas = _buscar_por_nombre(nombre, _es_contexto, raiz_skill, u)
            if halladas:
                contexto = halladas[0]
                break
    if contexto is None:
        raise CorpusError(MENSAJE_SIN_CONTEXTO)
    u.contexto = contexto.resolve()
    propios = _documentos_del_skill(u.contexto)
    if propios is not None:
        u.documentos = propios
        return u
    hermana = u.contexto.parent / SKILL_DOCUMENTOS                 # estructura anterior
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
    """Carpeta que contiene scripts/: el skill fuente-corpus (o el repositorio)."""
    for p in Path(__file__).resolve().parents:
        if p.name == "scripts":
            return p.parent
    return Path(__file__).resolve().parents[3]


def describir_ubicacion(raiz_skill, entorno=None):
    """Lineas con donde esta el skill y como ejecutar corpus.py, aunque falte algo."""
    raiz_skill = Path(raiz_skill)
    script = raiz_skill / "scripts" / "corpus.py"
    lineas = ["UBICACIÓN DEL CORPUS"]
    try:
        u = resolver_ubicacion(raiz_skill, entorno)
        lineas += [f"skill fuente-corpus: {u.contexto}", f"documentos: {u.documentos}"]
        lineas += ["AVISO: " + a for a in u.avisos]
        lineas += [f"corpus.py: {script}",
                   f'Ejecútalo desde cualquier carpeta: python "{script}" <comando>   (por ejemplo: verificar, catalogo)']
    except CorpusError as e:
        lineas += [f"skill fuente-corpus: {raiz_skill}", f"ERROR: {e.mensaje}",
                   "Para localizar el skill: find /home/oai/skills -type f -path '*fuente-corpus/scripts/corpus.py' 2>/dev/null"]
    return lineas


def incluir_no_vigentes(entorno=None):
    entorno = os.environ if entorno is None else entorno
    return entorno.get(VARIABLE_NO_VIGENTES, "").strip().lower() in ("1", "true", "si", "sí")
